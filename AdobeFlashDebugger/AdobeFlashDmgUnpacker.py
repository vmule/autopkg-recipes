#!/usr/bin/python
#
# Copyright 2010 Per Olofsson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""See docstring for AdobeFlashDmgUnpacker class"""

###
###

import os
import fileinput
import FoundationPlist
import re
import shutil
import subprocess
import tempfile

from autopkglib import Processor, ProcessorError


__all__ = ["AdobeFlashDmgUnpacker"]


class AdobeFlashDmgUnpacker(Processor):
    """Mounts a Flash dmg and extracts the Player pkg payload to pkgroot."""
    description = __doc__
    input_variables = {
        "finalize_script_path": {
            "required": True,
            "description":
                "Path to folder containing the Flash player postflight script.",
        },
        "pkgroot": {
            "required": True,
            "description":
                "Path to where the new package root will be created.",
        },
    }
    output_variables = {
        "version": {
            "description": "Version of the flash plugin.",
        },
    }

    def read_bundle_info(self, path):
        """Read Contents/Info.plist inside a bundle."""
        #pylint: disable=no-self-use
        try:
            info = FoundationPlist.readPlist(
                os.path.join(path, "Contents", "Info.plist"))
        except FoundationPlist.FoundationPlistException as err:
            raise ProcessorError(err)
        return info

    def decompress_plugin(self, finalize_script_path, pkgroot):
        '''Patches postflight binary to decompress the Flash Player.plugin'''
        #pylint: disable=no-self-use
        # Create temporary directory that we'll use to uncompress the plugin
        temp_path = tempfile.mkdtemp(prefix="flashXX", dir="/private/tmp")
        try:
            # temp path length must match original path length or our
            # patching can't possibly work
            if len(temp_path) != len("/Library/Internet Plug-Ins"):
                raise ProcessorError("temp_path length mismatch.")

            # Move Flash Player.plugin.lzma to our temp_path
            src = os.path.join(
                pkgroot, "Library/Internet Plug-Ins/Flash Player.plugin.lzma")
            try:
                shutil.move(src, temp_path)
            except (OSError, IOError):
                raise ProcessorError(
                    "Couldn't move %s to %s" % (src, temp_path))

            # Patch postflight executable.
            # It's hard-coded to work on
            # "/Library/Internet Plug-Ins/Flash Player.plugin.lzma",
            # so patch with a pathname the exact same length and
            # hope for the best...
            original_postflight_path = os.path.join(finalize_script_path,
                                                    "finalize")
            with open(original_postflight_path, "rb") as fref:
                postflight = fref.read()
            patched_postflight_path = os.path.join(temp_path, "finalize")
            with open(patched_postflight_path, "wb") as fref:
                fref.write(postflight.replace(
                    "/Library/Internet Plug-Ins", temp_path))
            os.chmod(patched_postflight_path, 0700)

            # Run patched postflight to unpack plugin.
            subprocess.check_call(patched_postflight_path)

            # Check to see if we got a uncompressed plugin where we expect
            plugin_path = os.path.join(temp_path, "Flash Player.plugin")
            if not os.path.isdir(plugin_path):
                raise ProcessorError("Unpacking Flash plugin failed.")

            # Move plugin back into pkgroot.
            plugin_destination = os.path.join(
                pkgroot, "Library/Internet Plug-Ins/Flash Player.plugin")
            shutil.copytree(plugin_path, plugin_destination, symlinks=True)

            shutil.rmtree(os.path.join(pkgroot, 'Library/PreferencePanes'))

        finally:
            shutil.rmtree(temp_path)

    def main(self):
        try:
            pkgroot = self.env['pkgroot']
            finalize_script_path = self.env['finalize_script_path']

            # decompress the actual plugin
            self.decompress_plugin(finalize_script_path, pkgroot)

            # Read version of plugin
            plugin_path = os.path.join(
                pkgroot, "Library/Internet Plug-Ins/Flash Player.plugin")
            info = self.read_bundle_info(plugin_path)
            self.env["version"] = info["CFBundleShortVersionString"]

        except BaseException as err:
            raise ProcessorError(err)

if __name__ == '__main__':
    PROCESSOR = AdobeFlashDmgUnpacker()
    PROCESSOR.execute_shell()
