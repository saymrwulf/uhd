//
// Copyright 2010-2011 Ettus Research LLC
// Copyright 2018 Ettus Research, a National Instruments Company
//
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include <uhd/exception.hpp>
#include <uhd/utils/paths.hpp>
#include <uhd/utils/static.hpp>
#include <uhdlib/utils/paths.hpp>
#include <boost/filesystem.hpp>
#include <boost/format.hpp>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = boost::filesystem;

/***********************************************************************
 * Module Load Function
 **********************************************************************/
#ifdef HAVE_DLOPEN
#    include <dlfcn.h>
static void load_module(const std::string& file_name)
{
    if (dlopen(file_name.c_str(), RTLD_LAZY) == NULL) {
        throw uhd::os_error(
            str(boost::format("dlopen failed to load \"%s\"") % file_name));
    }
}
#endif /* HAVE_DLOPEN */


#ifdef HAVE_LOAD_LIBRARY
#    include <windows.h>
static void load_module(const std::string& file_name)
{
    if (LoadLibrary(file_name.c_str()) == NULL) {
        throw uhd::os_error(
            str(boost::format("LoadLibrary failed to load \"%s\"") % file_name));
    }
}
#endif /* HAVE_LOAD_LIBRARY */


#ifdef HAVE_LOAD_MODULES_DUMMY
static void load_module(const std::string& file_name)
{
    throw uhd::not_implemented_error(str(
        boost::format("Module loading not supported: Cannot load \"%s\"") % file_name));
}
#endif /* HAVE_LOAD_MODULES_DUMMY */

/***********************************************************************
 * Load Modules
 **********************************************************************/
/*!
 * Load all modules in a given path.
 * This will recurse into sub-directories.
 * Does not throw, prints to std error.
 * \param path the filesystem path
 */
static void load_module_path(const fs::path& path)
{
    if (not fs::exists(path)) {
        // std::cerr << boost::format("Module path \"%s\" not found.") % path.string() <<
        // std::endl;
        return;
    }

    // try to load the files in this path
    if (fs::is_directory(path)) {
        for (fs::directory_iterator dir_itr(path); dir_itr != fs::directory_iterator();
             ++dir_itr) {
            load_module_path(dir_itr->path());
        }
        return;
    }

    // its not a directory, try to load it
    try {
        load_module(path.string());
    } catch (const std::exception& err) {
        std::cerr << boost::format("Error: %s") % err.what() << std::endl;
    }
}

namespace {

// Load all modules listed in a given directory.
//
// This will:
// - Open each file in the directory
// - Read each line from the file
// - Load the module named by each line
void load_module_d_path(const fs::path& path)
{
    for (fs::directory_iterator dir_itr(path); dir_itr != fs::directory_iterator();
         ++dir_itr) {
        if (fs::is_regular_file(dir_itr->path())) {
            // read file into lines
            std::ifstream file(dir_itr->path().string().c_str());
            std::string line;
            while (std::getline(file, line)) {
                if (line.empty() or line[0] == '#') {
                    continue;
                }
                load_module(line);
            }
        }
    }
}

} /* anonymous namespace */


/*!
 * Load all the modules given in the module paths.
 */
UHD_STATIC_BLOCK(load_modules)
{
    for (const fs::path& path : uhd::get_module_paths()) {
        load_module_path(path);
    }
    for (const fs::path& path : uhd::get_module_d_paths()) {
        if (fs::is_directory(path)) {
            load_module_d_path(path);
        }
    }
}
