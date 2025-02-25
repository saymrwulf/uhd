#
# Copyright ${year} Ettus Research, a National Instruments Brand
#
# SPDX-License-Identifier: LGPL-3.0-or-later
#

${"##################################################"}
# RFNoC Block Sources
${"##################################################"}
# Here, list all the files that are necessary to synthesize this block. Don't
# include testbenches!
# Make sure that the source files are nicely detectable by a regex. Best to put
# one on each line.
# The first argument to addprefix is the current path to this Makefile, so the
# path list is always absolute, regardless of from where we're including or
# calling this file. RFNOC_OOT_SRCS needs to be a simply expanded variable
# (not a recursively expanded variable), and we take care of that in the build
# infrastructure.
${ blockname_full.upper() }_SRCS := $(addprefix $(dir $(abspath $(lastword $(MAKEFILE_LIST)))), ${"\\"}
rfnoc_block_${config['module_name']}.sv ${"\\"}
noc_shell_${config['module_name']}.sv ${"\\"}
)
