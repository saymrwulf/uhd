#!/usr/bin/env python3
#
# Copyright 2024 Ettus Research, a National Instruments Brand
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""Demonstrates how to send and receive OFDM frames using the RFNoC OFDM block.

All ports of either one or two daughter boards can be used in this example. The
transmitted and received data is plotted as a frequency spectrum.

A cyclic prefix (CP) schedule can provided, in which case the OFDM tx block will
do CP insertion and the OFDM rx block will do CP removal.

The data flow is as follows:

    Host Tx Streamer ─> OFDM Tx ─> DUC ─> Radio Tx ─>──┐
                                                       │
    ┌────────────< RF / Digital Loopback <─────────────┘
    │
    └─> Radio Rx ─> DDC ─> OFDM Rx ─> Host Rx Streamer

It assumes the RFNoC topology like the one shown below. The configuration of the
SFPs may be 10 GbE (1 to 4 ports) or 100 GbE. The number of channels per radio
and DDC/DUC pair can be 1 or 2, with the DDC/DUC being optional. The following
diagram shows one channel per radio for simplicity.

                     ┌────────────┐        Ch0   ┌─────────┐     ┌─────────┐     ┌─────────┐
                     │            ├─────────────>│         ├────>│         ├────>│         │
                     │        sep0│        Ch1   │  OFDM#0 │     │  DUC#0  │     │Tx       │
                     │            │<───┐ ┌──────>│         ├────>│         ├────>│         │
                     │            │    │ │       └─────────┘     └─────────┘     │         │
 ┌──────┐    sfp0    │            │  ┌─┼─┘                                       │ Radio#0 │
 │      │<──────────>│            │  │ │   Ch0   ┌─────────┐     ┌─────────┐     │         │
 │      │            │            ├──┘ └─────────┤         │<────┤         │<────┤         │
 │      │    sfp1    │        sep1│        Ch1   │  OFDM#1 │     │  DDC#0  │     │Rx       │
 │      │<──────────>│            │<─────────────┤         │<────┤         │<────┤         │
 │ Host │            │            │              └─────────┘     └─────────┘     └─────────┘
 │      │    sfp2    │    RFNoC   │
 │      │<──────────>│  Crossbar  │
 │      │            │            │
 │      │    sfp3    │            │        Ch2   ┌─────────┐     ┌─────────┐     ┌─────────┐
 │      │<──────────>│            ├─────────────>│         ├────>│         ├────>│         │
 └──────┘            │        sep2│        Ch3   │  OFDM#2 │     │  DUC#1  │     │Tx       │
                     │            │<───┐ ┌──────>│         ├────>│         ├────>│         │
                     │            │    │ │       └─────────┘     └─────────┘     │         │
                     │            │  ┌─┼─┘                                       │ Radio#1 │
                     │            │  │ │   Ch2   ┌─────────┐     ┌─────────┐     │         │
                     │            ├──┘ └─────────┤         │<────┤         │<────┤         │
                     │        sep3│        Ch3   │  OFDM#3 │     │  DDC#1  │     │Rx       │
                     │            │<─────────────┤         │<────┤         │<────┤         │
                     └────────────┘              └─────────┘     └─────────┘     └─────────┘

"""

import argparse

import matplotlib.pyplot as plt
import numpy as np
import uhd
import math
from matplotlib.widgets import Slider

graph_connections = {
    0: {
        "tx": [("0/OFDM#0", 0, "0/DUC#0", 0, "0/Radio#0", 0)],
        "rx": [("0/Radio#0", 0, "0/DDC#0", 0, "0/OFDM#1", 0)],
    },
    1: {
        "tx": [("0/OFDM#0", 1, "0/DUC#0", 1, "0/Radio#0", 1)],
        "rx": [("0/Radio#0", 1, "0/DDC#0", 1, "0/OFDM#1", 1)],
    },
    2: {
        "tx": [("0/OFDM#2", 0, "0/DUC#1", 0, "0/Radio#1", 0)],
        "rx": [("0/Radio#1", 0, "0/DDC#1", 0, "0/OFDM#3", 0)],
    },
    3: {
        "tx": [("0/OFDM#2", 1, "0/DUC#1", 1, "0/Radio#1", 1)],
        "rx": [("0/Radio#1", 1, "0/DDC#1", 1, "0/OFDM#3", 1)],
    },
}


def complex128_to_sc16(data, scale=32767):
    """Convert complex128 NumPy to sc16 stores as uint32."""
    real = np.int16(np.real(data) * scale)
    imag = np.int16(np.imag(data) * scale)
    return np.uint32((np.uint32(imag) << 16) | (np.uint32(real) & 0xFFFF))


def sc16_to_complex128(data):
    """Convert sc16 stored as uint32 to complex128 NumPy."""
    real = np.array(np.int16(data & 0xFFFF), dtype=np.float64) / 32767
    imag = np.array(np.int16((data >> 16) & 0xFFFF), dtype=np.float64) / 32767
    return np.array(real + 1j * imag, dtype=np.complex128)


def parse_args():
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-a",
        "--args",
        type=str,
        default="",
        help="Device args (e.g., addr=192.168.10.2)",
    )
    parser.add_argument(
        "-s",
        "--fft-size",
        type=int,
        default=4096,
        help="FFT size (default = 4096)",
    )
    parser.add_argument(
        "-n",
        "--num-symbols",
        type=int,
        default=14,
        help="Number of symbols to transmit/receive (default=14)",
    )
    parser.add_argument(
        "-y",
        "--amplitude",
        type=float,
        default=0.5,
        help="Amplitude of the tone",
    )
    parser.add_argument(
        "-p",
        "--cp-list",
        type=int,
        nargs="+",
        default=[],
        help="List of cyclic prefix lengths to use (default=[])",
    )
    parser.add_argument(
        "-c",
        "--channels",
        type=str,
        choices=["0", "0,1", "2,3", "0,1,2,3"],
        default="0,1",
        help="The channels to use (default=0,1)",
    )
    parser.add_argument(
        "-l",
        "--loopback",
        action="store_true",
        help="Use internal loopback",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=int,
        default=None,
        help="The number of cycles to delay RX vs. TX when streaming",
    )
    parser.add_argument(
        "--tx-gain",
        type=int,
        default=15,
        help="The TX gain (default=15)",
    )
    parser.add_argument(
        "--rx-gain",
        type=int,
        default=50,
        help="The RX gain (default=50)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        help="The TX/RX rate of host data (default is master clock rate)",
    )
    return parser.parse_args()


def print_args(args):
    """Print the used arguments."""
    print("using arguments:")
    for key, value in args.__dict__.items():
        if isinstance(value, list):
            print(f"--{key.replace('_','-')} {' '.join([str(x) for x in value])}")
        else:
            print(f"--{key.replace('_','-')} {value}")


def create_block_controller(block):
    """Create block controller for a given RfNoc block."""
    name = block.get_unique_id()
    if name[2:].startswith("Radio"):
        block = uhd.rfnoc.RadioControl(block)
    elif name[2:].startswith("OFDM"):
        block = uhd.rfnoc.OfdmBlockControl(block)
    elif name[2:].startswith("DDC"):
        block = uhd.rfnoc.DdcBlockControl(block)
    elif name[2:].startswith("DUC"):
        block = uhd.rfnoc.DucBlockControl(block)
    else:
        raise NotImplementedError(f"Cannot create controller for block {name}")
    return block


def connect_graph(graph, graph_connections, channels=[], tx_streamer=None, rx_streamer=None):
    """Connect the RfNoc graph and create the block controllers automatically."""
    controllers = dict()
    for chan_idx, chan in enumerate(channels):
        for direction in ["tx", "rx"]:
            print(f"Connections for channel {chan}/{direction.upper()}:")
            connections = graph_connections[chan][direction]
            for idx, (src_name, src_idx, cvtr_name, cvtr_idx, dst_name, dst_idx) in enumerate(connections):
                first = idx == 0
                last = idx == (len(connections) - 1)
                if src_name not in controllers:
                    # create block controller if it not yet existing
                    controllers[src_name] = create_block_controller(graph.get_block(src_name))
                if dst_name not in controllers:
                    # create block controller if it not yet existing
                    controllers[dst_name] = create_block_controller(graph.get_block(dst_name))
                if direction == "tx" and first and tx_streamer is not None:
                    # connect TX streamer
                    print(f"    TX streamer/port{chan_idx} -> {src_name}/port{src_idx}")
                    graph.connect(
                        tx_streamer,
                        chan_idx,
                        controllers[src_name].get_unique_id(),
                        src_idx,
                    )
                # make requested connection
                print(f"    {src_name}/port{src_idx} -> {dst_name}/port{dst_idx}")
                uhd.rfnoc.connect_through_blocks(
                    graph,
                    controllers[src_name].get_unique_id(),
                    src_idx,
                    controllers[dst_name].get_unique_id(),
                    dst_idx,
                )
                # check if the image has an up or down converter, which are optional
                try:
                    controllers[cvtr_name] = create_block_controller(
                        graph.get_block(cvtr_name)
                    )
                except RuntimeError:
                    pass
                if direction == "rx" and last and rx_streamer is not None:
                    # connect RX streamer
                    print(f"    {dst_name}/port{dst_idx} -> RX streamer/port{chan_idx}")
                    graph.connect(
                        controllers[dst_name].get_unique_id(),
                        dst_idx,
                        rx_streamer,
                        chan_idx,
                    )
    return (graph, controllers.values())


def configure_radio_block(radio, spp, tx_gain=None, rx_gain=None, digital_loopback=False):
    """Configure the Radio block."""
    for blk_chan_idx in range(radio.get_num_input_ports()):
        # if the loopback argument was provided, enable the digital loopback
        # inside in the radio block. No external connection is required on the
        # USRP.
        radio.poke32(0x1000 + 128 * blk_chan_idx, int(digital_loopback))

        # Set the radio's RX packet size
        radio.set_properties("spp=" + str(spp), blk_chan_idx)

        if not digital_loopback:
            # Set TX gain and RX gain
            if tx_gain is not None:
                radio.set_tx_gain(tx_gain, blk_chan_idx)
            if rx_gain is not None:
                radio.set_rx_gain(rx_gain, blk_chan_idx)


def print_ofdm_block_info(ofdm):
    """Print OFDM block information."""
    print(f"Maximum FFT size: {ofdm.get_max_fft_size()}")
    print(f"Maximum CP size: {ofdm.get_max_cp_length()}")
    print(f"Maximum CP insertion list length: {ofdm.get_max_cp_ins_list_length()}")
    print(f"Maximum CP removal list length: {ofdm.get_max_cp_rem_list_length()}")


def default_scaling(fft_size):
    """Return the scaling value for the default 1/N scaling"""
    # 1/N scaling should be 1010...10 if fft_size is a power of 4 and 0110...10
    # if fft_size is not a power of 4.
    #
    # Examples: FFT size 4096 => 0b101010101010
    #           FFT size 2048 => 0b011010101010
    #
    # See Xilinx Fast Fourier Transform v9.1 Product Guide (PG901) for details.
    fft_scale = 0
    fft_size_log2 = int(math.log2(fft_size))
    for i in range((fft_size_log2+1)//2-1, -1, -1):
        stage = 0b01 if i == fft_size_log2//2 else 0b10
        fft_scale = (fft_scale << 2) | stage
    return fft_scale


def configure_ofdm_block(ofdm, fft_size, cp_list=[]):
    """Configure the OFDM block."""
    # The argument cp_list contains the cyclic prefix length that
    # shell be used for cyclic prefix insertion (in the TX path) and for cyclic
    # prefix removal (in the RX path)
    #
    # example:
    # cp_list = [352, 288, 288, 288, 288, 288, 288, 288, 288, 288, 288, 288, 288, 288]

    # TODO: The block controller should check the compat and error if it's not
    # compatible with the driver.

    # TODO: The block controller API should have functions for reading the
    # capabilities and should check settings provided by the user to ensure
    # they're compatible.

    ifft_scale = 0 # No scaling
    fft_scale = default_scaling(fft_size) # Default 1/N scaling

    # clear cp insertion / removal FIFOs
    ofdm.clear_cp_insertion_fifo()
    ofdm.clear_cp_removal_fifo()

    # set FFT size
    ofdm.set_fft_size(fft_size)

    unique_id = ofdm.get_unique_id()
    if unique_id in ["0/OFDM#0", "0/OFDM#2"]:
        # OFDM block is in TX path -> configure OFDM block for inverse FFT
        ofdm.set_fft_direction(uhd.libpyuhd.rfnoc.ofdm_direction.REVERSE)
        ofdm.set_fft_scaling(ifft_scale)
        if len(cp_list):
            ofdm.load_cp_insertion_fifo(cp_list)
    elif unique_id in ["0/OFDM#1", "0/OFDM#3"]:
        # OFDM block is in RX path -> configure OFDM block for normal FFT
        ofdm.set_fft_direction(uhd.libpyuhd.rfnoc.ofdm_direction.FORWARD)
        ofdm.set_fft_scaling(fft_scale)
        if len(cp_list):
            ofdm.load_cp_removal_fifo(cp_list)
    else:
        raise NotImplementedError(f"Don't know how to configure block {unique_id}")


def create_symbols(channels, num_symbols, fft_size, amplitude):
    """Create symbols with a single tone per symbol."""
    num_chan = len(channels)
    symbols = np.zeros((num_chan, num_symbols * fft_size), dtype=np.complex128)
    for chan_idx, chan in enumerate(channels):
        for symbol_index in range(num_symbols):
            start = symbol_index * fft_size
            end = start + fft_size
            # create single tone at 'subcarrier' with 'amplitude'
            symbol_data = np.zeros(fft_size, dtype=np.complex128)
            subcarrier = ((chan + 1) * fft_size) // (num_chan * 4)
            subcarrier += symbol_index
            symbol_data[subcarrier] = amplitude
            symbols[chan_idx][start:end] = symbol_data
    return symbols


def total_cp_length(cp_list, num_symbols):
    """Calculate the samples added by the cyclic prefix insertion."""
    if len(cp_list) == 0:
        return 0
    sum = 0
    for count in range(num_symbols):
        sum += cp_list[count % len(cp_list)]
    return sum


def get_tx_rx_delay(radio, args):
    """Determine the loopback delay."""
    tick_rate = radio.get_tick_rate()
    if args.delay is not None:
        loopback_delay = args.delay
    elif args.loopback:
        # With internal digital loopback, there's a fixed delay between TX and RX
        if tick_rate in [122.88e6, 125.0e6]:
            # Add 2 cycles for 100 MHz FPGA
            loopback_delay = 2
        elif tick_rate in [245.76e6, 250.0e6]:
            # Add 12 cycles for 200 MHz FPGA
            loopback_delay = 12
        else:
            raise NotImplementedError("unsupported tick rate: {:.02f} MS/s".format(tick_rate / 1e6))
    else:
        # With RF loopback there's a fixed delay between TX and RX
        if tick_rate in [245.76e6, 250.0e6]:
            # Add 188 cycles for 200 MHz FPGA
            loopback_delay = 188
        else:
            raise NotImplementedError()
    return loopback_delay / tick_rate


def transmit_and_receive(
    tx_streamer, rx_streamer, tx_time, data_in, rx_time, data_out_size, num_samps
):
    """Transmit and receive.

    Issue receive command for the future time to capture the data when it is
    transmitted. We must also account for the cyclic prefix length, which
    means our acquisition length needs to be longer.
    """
    stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    stream_cmd.stream_now = False
    stream_cmd.time_spec = uhd.types.TimeSpec(rx_time)
    stream_cmd.num_samps = num_samps
    rx_streamer.issue_stream_cmd(stream_cmd)

    # Send symbols to the OFDM tx block
    tx_md = uhd.types.TXMetadata()
    tx_md.time_spec = uhd.types.TimeSpec(tx_time)
    tx_md.has_time_spec = True
    tx_md.start_of_burst = True
    tx_md.end_of_burst = True
    num_tx = tx_streamer.send(data_in, tx_md, timeout=5.0)
    print(f"Sent {num_tx} samples")

    # Receive the result from the OFDM rx block
    rx_md = uhd.types.RXMetadata()
    data_out = np.zeros(data_out_size, dtype=np.uint32)
    num_rx = 0
    num_rx = rx_streamer.recv(data_out, rx_md, 5.0)
    print(f"Received {num_rx} samples")

    if num_rx < num_tx:
        raise RuntimeError("ERROR: number of received samples is too low")

    return data_out


def find_peak(
    data_in,
    data_out,
    symbols_in,
    symbols_out,
    symbol_index,
    fft_size,
    channels,
    threshold=0.5,
):
    """Find the peaks."""
    print(f"\npeaks for symbol {symbol_index}")
    start = symbol_index * fft_size  # First sample of FFT
    end = start + fft_size  # Last sample of FFT (plus 1)
    peaks_in = [[] for chan in channels]
    peaks_out = [[] for chan in channels]
    for chan_idx, chan in enumerate(channels):
        threshold_in = threshold * max([np.abs(x) for x in symbols_in[chan_idx][start:end]])
        threshold_out = threshold * max([np.abs(x) for x in symbols_out[chan_idx][start:end]])
        for i in range(start, end):
            mag = np.abs(symbols_in[chan_idx][i])
            if mag > threshold_in:
                real = np.int16(data_in[chan_idx][i] & 0xFFFF)
                imag = np.int16((data_in[chan_idx][i] >> 16) & 0xFFFF)
                if (abs(real) >= 4) or (abs(imag) >= 4):
                    # filter out peaks which are below the noise level
                    print(f"Chan {chan} input peak at {i % fft_size} of {real}{imag:+d}j")
                    peaks_in[chan_idx].append(i % fft_size)
            mag = np.abs(symbols_out[chan_idx][i])
            if mag > threshold_out:
                real = np.int16(data_out[chan_idx][i] & 0xFFFF)
                imag = np.int16((data_out[chan_idx][i] >> 16) & 0xFFFF)
                if (abs(real) >= 4) or (abs(imag) >= 4):
                    # filter out peaks which are below the noise level
                    print(f"Chan {chan} output peak at {i % fft_size} of {real}{imag:+d}j")
                    peaks_out[chan_idx].append(i % fft_size)
    return (peaks_in, peaks_out)


def update_plot(
    axes, symbols_in, symbols_out, symbol_index, fft_size, channels, peaks_in, peaks_out
):
    """Plot the input sent and output received for the selected FFT."""
    freq_bins = np.arange(0, fft_size)
    start = symbol_index * fft_size  # First sample of FFT
    end = start + fft_size  # Last sample of FFT (plus 1)
    for chan_idx, chan in enumerate(channels):
        col = chan_idx
        for row in range(3):
            ax = axes[row][col]
            ax.clear()
            if row == 0:
                # 1st row: input data, real/imag amplitude
                ax.set_title(f"Channel {chan} / symbol {symbol_index}")
                if col == 0:
                    ax.set_ylabel("Amplitude In")
                ax.set_yscale("log")
                ax.plot(freq_bins, np.real(symbols_in[chan_idx][start:end]), label="I")
                ax.plot(freq_bins, np.imag(symbols_in[chan_idx][start:end]), label="Q")
                for i in peaks_in[chan_idx]:
                    mag = np.abs(symbols_in[chan_idx][start + i])
                    deg = np.angle(symbols_in[chan_idx][start + i], deg=True)
                    ax.text(
                        i,
                        mag,
                        f" {i}:\n {mag:.02e}\n {deg:.0f}°",
                        horizontalalignment="left",
                        verticalalignment="top",
                    )
                ax.legend()
                ax.grid(True)
            elif row == 1:
                # 2nd row: output data, real/imag amplitude
                if col == 0:
                    ax.set_ylabel("Amplitude Out")
                ax.set_yscale("log")
                ax.plot(freq_bins, abs(np.real(symbols_out[chan_idx][start:end])), label="I")
                ax.plot(freq_bins, abs(np.imag(symbols_out[chan_idx][start:end])), label="Q")
                for i in peaks_out[chan_idx]:
                    mag = np.abs(symbols_out[chan_idx][start + i])
                    deg = np.angle(symbols_out[chan_idx][start + i], deg=True)
                    ax.text(
                        i,
                        mag,
                        f" {i}:\n {mag:.02e}\n {deg:.0f}°",
                        horizontalalignment="left",
                        verticalalignment="top",
                    )
                ax.legend()
                ax.grid(True)
            elif row == 2:
                # 3rd row: output data, magnitude in dB
                if col == 0:
                    ax.set_ylabel("Magnitude [dB]")
                ax.set_xlabel("Frequency Bin")
                ax.set_yscale("linear")
                mag = np.abs(symbols_out[chan_idx][start:end])
                # Clip the magnitude to avoid div by 0 warning and -inf in the plot
                mag_clip = np.clip(mag, 1/2**16, math.inf)
                power_values = np.multiply(np.log(mag_clip), 20)
                ax.plot(freq_bins, power_values)
                for i in peaks_out[chan_idx]:
                    ax.text(
                        i,
                        power_values[i],
                        f" {i}:\n {power_values[i]:.2f} dB",
                        horizontalalignment="left",
                        verticalalignment="top",
                    )
                ax.grid(True)


def main():
    """Main function of the example."""
    args = parse_args()
    print_args(args)

    # convert the channels to a list of integers
    channels = [int(x) for x in args.channels.split(",")]
    num_chan = len(channels)

    # Fetch the arguments
    fft_size = args.fft_size
    num_symbols = args.num_symbols

    # Choose a "samples per packet" (SPP) to use that evenly divides the FFT
    # size but won't exceed the USRPs 8 KB packet size limit (with header).
    spp = fft_size
    while spp > 1996:
        spp = spp // 2
    print(f"Using samples per packet of {spp}")

    # Get references for OFDM and radio blocks
    graph = uhd.rfnoc.RfnocGraph(args.args)

    # Create TX and RX streamers
    sa = uhd.usrp.StreamArgs("sc16", "sc16")
    sa.args = f"spp={spp}"
    tx_streamer = graph.create_tx_streamer(len(channels), sa)
    rx_streamer = graph.create_rx_streamer(len(channels), sa)

    # Connect the blocks for the given channels
    graph, blocks = connect_graph(graph, graph_connections, channels, tx_streamer, rx_streamer)

    # Put OFDM blocks and Radio blocks in dedicated lists
    ofdm_blocks = [x for x in blocks if isinstance(x, uhd.libpyuhd.rfnoc.ofdm_block_control)]
    radio_blocks = [x for x in blocks if isinstance(x, uhd.libpyuhd.rfnoc.radio_control)]
    duc_blocks = [x for x in blocks if isinstance(x, uhd.libpyuhd.rfnoc.duc_block_control)]
    ddc_blocks = [x for x in blocks if isinstance(x, uhd.libpyuhd.rfnoc.ddc_block_control)]

    # Commit the graph
    graph.commit()

    # configure the Radio blocks
    for radio in radio_blocks:
        configure_radio_block(
            radio,
            spp,
            rx_gain=args.rx_gain,
            tx_gain=args.tx_gain,
            digital_loopback=args.loopback,
        )

    # Configure the DDC/DUC rates
    if args.rate:
        for duc in duc_blocks:
            for chan in range(duc.get_num_input_ports()):
                print(
                    f"Attempting to set {duc.get_unique_id()}.{chan} to {args.rate/1e6} MHz... ",
                    end="",
                )
                duc.set_input_rate(args.rate, chan)
                print(f"Actual rate is {duc.get_input_rate(chan)/1e6} MHz")
        for ddc in ddc_blocks:
            for chan in range(ddc.get_num_input_ports()):
                print(
                    f"Attempting to set {ddc.get_unique_id()}.{chan} to {args.rate/1e6} MHz...",
                    end="",
                )
                ddc.set_output_rate(args.rate, chan)
                print(f"Actual rate is {ddc.get_output_rate(chan)/1e6} MHz")

    # Read and display OFDM block information
    print_ofdm_block_info(ofdm_blocks[0])

    # configure the OFDM blocks
    for ofdm in ofdm_blocks:
        configure_ofdm_block(ofdm, fft_size=args.fft_size, cp_list=args.cp_list)

    # Create a set of symbols to send
    symbols_in = create_symbols(
        channels=channels,
        num_symbols=num_symbols,
        fft_size=fft_size,
        amplitude=args.amplitude,
    )
    # convert TX data from complex floating point to I16/I16
    data_in = complex128_to_sc16(symbols_in)

    # Transmit and receive
    radio = radio_blocks[0]
    tx_time = radio.get_time_now().get_real_secs() + 1.0
    data_out = transmit_and_receive(
        tx_streamer=tx_streamer,
        rx_streamer=rx_streamer,
        tx_time=tx_time,
        rx_time=tx_time + get_tx_rx_delay(radio, args),
        data_in=data_in,
        data_out_size=(num_chan, args.num_symbols * args.fft_size),
        num_samps=args.fft_size * args.num_symbols
        + total_cp_length(args.cp_list, args.num_symbols),
    )

    # Convert RX data from I16/I16 to complex floating point
    symbols_out = sc16_to_complex128(data_out)

    def update(symbol_index):
        """Callback function of the slider.

        find peaks and update plots for the given symbol_index
        """
        symbol_index = int(symbol_index)
        peaks_in, peaks_out = find_peak(
            data_in, data_out, symbols_in, symbols_out, symbol_index, fft_size, channels
        )
        update_plot(
            axes,
            symbols_in,
            symbols_out,
            symbol_index,
            fft_size,
            channels,
            peaks_in,
            peaks_out,
        )

    fig, axes = plt.subplots(3, num_chan, figsize=(14, 8))
    if num_chan == 1:
        # Keep the array shape consistent, even if it's a single channel
        axes = axes.reshape(-1, 1)
    # show the first symbol
    update(symbol_index=0)
    fig.subplots_adjust(right=0.9)
    ax_slider = fig.add_axes([0.93, 0.12, 0.02, 0.75], facecolor="gray")
    symbol_slider = Slider(
        ax=ax_slider,
        label="Symbol",
        valmin=0,
        valmax=num_symbols - 1,
        valinit=0,
        valstep=1,
        valfmt="%d",
        orientation="vertical",
    )
    symbol_slider.on_changed(update)
    try:
        plt.show(block=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
