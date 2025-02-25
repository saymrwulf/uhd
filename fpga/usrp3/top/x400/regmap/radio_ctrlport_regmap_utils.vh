//
// Copyright 2023 Ettus Research, A National Instruments Company
//
// SPDX-License-Identifier: LGPL-3.0-or-later
//
// Module: radio_ctrlport_regmap_utils.vh
// Description:
// The constants in this file are autogenerated by XmlParse.

//===============================================================================
// A numerically ordered list of registers and their HDL source files
//===============================================================================

  // DB_WINDOW          : 0x0 (x4xx_core_common.v)
  // RFDC_TIMING_WINDOW : 0x8000 (x4xx_core_common.v)
  // RF_CORE_WINDOW     : 0xA000 (x4xx_core_common.v)
  // DIO_WINDOW         : 0xC000 (x4xx_core_common.v)

//===============================================================================
// RegTypes
//===============================================================================

//===============================================================================
// Register Group RADIO_CTRLPORT_WINDOWS
//===============================================================================

  // DB_WINDOW Window (from x4xx_core_common.v)
  localparam DB_WINDOW = 'h0; // Window Offset
  localparam DB_WINDOW_SIZE = 'h8000;  // size in bytes

  // RFDC_TIMING_WINDOW Window (from x4xx_core_common.v)
  localparam RFDC_TIMING_WINDOW = 'h8000; // Window Offset
  localparam RFDC_TIMING_WINDOW_SIZE = 'h2000;  // size in bytes

  // RF_CORE_WINDOW Window (from x4xx_core_common.v)
  localparam RF_CORE_WINDOW = 'hA000; // Window Offset
  localparam RF_CORE_WINDOW_SIZE = 'h2000;  // size in bytes

  // DIO_WINDOW Window (from x4xx_core_common.v)
  localparam DIO_WINDOW = 'hC000; // Window Offset
  localparam DIO_WINDOW_SIZE = 'h4000;  // size in bytes
