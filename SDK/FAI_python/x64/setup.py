#!/usr/bin/env python
from setuptools import setup, Extension
from setuptools.command.build_ext import new_compiler
from logging import info, warning, error

import argparse
import ctypes
import datetime
import glob
import stat
import os
import re
import shutil
import subprocess
import sys
import platform

################################################################################
def get_machinewidth():
    # From the documentation of 'platform.architecture()':
    #   "Note:
    #    On Mac OS X (and perhaps other platforms), executable files may be
    #    universal files containing multiple architectures. To get at the
    #    '64-bitness# of the current interpreter, it is more reliable to query
    #    the sys.maxsize attribute.
    #   "
    if sys.maxsize > 2147483647:
        return 64
    else:
        return 32

def get_platform():
    return platform.system()

def get_machine():
    return platform.machine()

class BuildSupport(object):

    # --- Constants ---
    RootDevDir = None

    BinPath = {
        ('Windows', 32): 'Win32',
        ('Windows', 64): 'x64',
        ('Linux', 32): 'lib',
        ('Linux', 64): 'lib64',
        ('Darwin', 64): 'lib64'
        } [ (get_platform(), get_machinewidth()) ]

    # Compatible swig versions
    SwigVersions = ["4.0.0"]
    SwigOptions = [
        "-Wextra",
        "-Wall",
        "-threads",
        #lots of debug output "-debug-tmsearch",
        ]

    # Where to place generated code
    GeneratedDir = os.path.join(".", "generated")

    # Directory of the final package
    PackageDir = os.path.join(".", "FAI_python")

    # What parts of the runtime should be deployed by default
    RuntimeDefaultDeploy = {
        "base",
        "genicam",
        "libpol",
        "libDemosaic"
        }

    # --- Attributes to be set by init (may be platform specific ---

    # swig executable to be called
    SwigExe = None

    # Library dirs for compiling extensions
    LibraryDirs = []

    # Macro definitions for compiling extensions
    DefineMacros = []

    # Additional compiler arguments for extensions
    ExtraCompileArgs = []

    # Additional linker arguments for extensions
    ExtraLinkArgs = []

    # Runtime files needed for copy deployment
    RuntimeFiles = {}

    def get_swig_includes(self):
        raise RuntimeError("Must be implemented by platform build support!")

    def __init__(self):
        self.SwigExe = "swig"
        if sys.version_info[0] == 3:
            self.SwigOptions.append("-py3")

    def dump(self):
        for a in dir(self):
            info("%s=%s" % (a, getattr(self, a)))

    def find_swig(self):
        # Find SWIG executable
        swig_executable = None
        for candidate in ["swig4.0", "swig"]:
            swig_executable = shutil.which(candidate)
            if self.is_supported_swig_version(swig_executable):
                info("Found swig: %s" % (swig_executable,))
                return swig_executable

        raise RuntimeError("swig executable not found on path!")

    def is_supported_swig_version(self, swig_executable):
        if swig_executable is None:
            return False

        try:
            output = subprocess.check_output(
                [swig_executable, "-version"],
                universal_newlines=True
                )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

        res = re.search(r"SWIG Version ([\d\.]+)", output)
        if res is None:
            return False

        if tuple(map(int, res.group(1).split('.'))) < (3, 0, 12):
            msg = (
                "The version of swig is %s which is too old. " +
                "Minimum required version is 3.0.12"
                )
            warning(msg, res.group(1))
            return False

        return True


    def call_swig(self, sourcedir, source, version, skip=False):
        name = os.path.splitext(source)[0]
        #  cpp_name = os.path.abspath(
        #      os.path.join(self.GeneratedDir, "%s_wrap.cpp" % name)
        #      )
        cpp_name = os.path.abspath(
            os.path.join(self.GeneratedDir, "%s_wrap.c" % name)
            )

        if skip:
            return cpp_name

        outdir = os.path.abspath(self.PackageDir)

        for inc in self.get_swig_includes():
            self.SwigOptions.append("-I%s" % inc)

        call_args = [self.SwigExe]
        call_args.extend(["-python"])
        call_args.extend(["-outdir", outdir])
        call_args.extend(["-o", cpp_name])
        call_args.extend(self.SwigOptions)
        call_args.append(source)

        print("call", " ".join(call_args))
        subprocess.check_call(call_args, cwd=os.path.abspath(sourcedir))

        # append module version property
        with open(os.path.join(outdir, "%s.py" % name), 'at') as gpf:
            gpf.write("\n__version__ = '%s'\n" % version)

        # Python needs an __init__.py inside the package directory...
        with open(os.path.join(bs.PackageDir, "__init__.py"), "a"):
            pass

        return cpp_name

    def copy_runtime(self):

        runtime_dir = os.path.join(
            self.RootDevDir,
            "lib/x64"
            )
        package_dir = os.path.abspath(self.PackageDir)
        for package in self.RuntimeDefaultDeploy:
            for src, dst in self.RuntimeFiles[package]:
                dst = os.path.join(package_dir, dst)
                if not os.path.exists(dst):
                    os.makedirs(dst)
                src = os.path.join(runtime_dir, src)
                for f in glob.glob(src):
                    print("Copy %s => %s" % (f, dst))
                    shutil.copy(f, dst)
            if package in self.RuntimeFolders:
                for src, dst in self.RuntimeFolders[package]:
                    dst = os.path.join(package_dir, dst)
                    src = os.path.join(runtime_dir, src)
                    shutil.rmtree(dst, ignore_errors=True)
                    print("Copy tree %s => %s" % (src, dst))
                    shutil.copytree(src, dst)


    def clean(self, mode, additional_dirs=None):
        if mode == 'skip':
            return
        clean_dirs = [self.GeneratedDir, self.PackageDir]
        if additional_dirs:
            clean_dirs.extend(additional_dirs)
        for cdir in clean_dirs:
            print("Remove:", cdir)
            shutil.rmtree(cdir, ignore_errors=True)
        if mode == 'keep':
            os.makedirs(self.GeneratedDir)
            os.makedirs(self.PackageDir)


    def use_debug_configuration(self):
        raise RuntimeError("Must be implemented by platform build support!")

    @staticmethod
    def get_git_version():
        try:
            # GIT describe as version
            git_version = subprocess.check_output(
                ["git", "describe", "--tags", "--dirty"],
                universal_newlines=True
                )
            git_version = git_version.strip()
            m_rel = re.match(
                r"^\d+(?:\.\d+){2,3}(?:(?:a|b|rc)\d*)?$",
                git_version
                )
            #this will match  something like 1.0.0-14-g123456 and
            # 1.0.0-14-g123456-dirty and 1.0.0-dirty
            rx_git_ver = re.compile(
                r"""
                ^(\d+(?:\.\d+){2,3}
                (?:(?:a|b|rc)\d*)?)
                (?:(?:\+[a-zA-Z0-9](?:[a-zA-Z0-9\.]*[a-zA-Z0-9]?))?)
                (?:-(\d+)-g[0-9a-f]+)?
                (?:-dirty)?$
                """,
                re.VERBOSE
                )
            m_dev = rx_git_ver.match(git_version)
            if m_rel:
                # release build -> return as is
                return git_version
            if m_dev:
                # development build
                return "%s.dev%s" % (m_dev.group(1), m_dev.group(2) or 0)

            warning("failed to parse git version '%s'", git_version)
            raise OSError
        except (OSError, subprocess.CalledProcessError) as e:
            warning("git not found or invalid tag found.")
            warning("-> Building version from date!")
            now = datetime.datetime.now()
            midnight = datetime.datetime(now.year, now.month, now.day)
            todays_seconds = (now - midnight).seconds
            return "%d.%d.%d.dev%d" % (
                now.year,
                now.month,
                now.day,
                todays_seconds
                )

    def get_version(self):
        git_version = self.get_git_version()
        return git_version

    def get_short_version(self, version):
        return version.split('+')[0]

    @staticmethod
    def make():
        if get_platform() == "Windows":
            return BuildSupportWindows()
        elif get_platform() == "Linux":
            return BuildSupportLinux()
        else:
            error("Unsupported platform")

    def get_package_data_files(self):
        # patterns for files in self.PackageDir
        data_files = ["*.dll", "*.zip", "*.so", "*.so.*"]

        # also add all files of any sub-directories recursively
        pdir = self.PackageDir
        for entry in os.listdir(self.PackageDir):
            jentry = os.path.join(pdir, entry)
            if stat.S_ISDIR(os.stat(jentry).st_mode):
                for (root, _, fnames) in os.walk(jentry):
                    for fname in fnames:
                        # file names have to be relative to self.PackageDir
                        jname = os.path.join(root, fname)
                        pdir_rel = os.path.relpath(jname, self.PackageDir)
                        data_files.append(pdir_rel)

        return data_files

################################################################################

class BuildSupportWindows(BuildSupport):

    # Base directory for FAI SDK on Windows
    RootDevDir = None

    RuntimeFiles = {

        "base": [
            ("FAI_c.dll", ""),
            ("facamera.dll", ""),
            #("camera.dll", ""),
            #("camera_gige.dll", ""),
            #("camera_u3v.dll", ""),
            #("device.dll", ""),
            #("genicam.dll", ""),
            #("gige_vision.dll", ""),
            #("grab_device.dll", ""),
            ("image.dll", ""),
            #("net.dll", ""),
            #("os.dll", ""),
            #("u3v.dll", ""),
            ("libusbK.dll", ""),
            ("opencv_world455.dll", ""),
            ("lsc_calibrate.dll", ""),
            ("libLSC.dll", ""),
            ],

        "genicam": [
            ("dll", ""),
            ("dll", ""),
            ("CLAllSerial_MD_*.dll", ""),
            ("CLProtocol_MD_*.dll", ""),
            ("FirmwareUpdate_MD_*.dll", ""),
            ("GCBase_MD_*.dll", ""),
            ("GenApiJava_MD_*.dll", ""),
            ("GenApi_MD_*.dll", ""),
            ("GenCP_MD_*.dll", ""),
            ("GenTLJava_MD_*.dll", ""),
            ("log4cpp_MD_*.dll", ""),
            ("Log_MD_*.dll", ""),
            ("MathParser_MD_*.dll", ""),
            ("NodeMapData_MD_*.dll", ""),
            ("XmlParser_MD_*.dll", ""),
            ],

        "libpol": [
            ("libpol.dll", ""),
            ],

        "libDemosaic": [
            ("libDemosaic.dll", ""),
            ],

        }

    RuntimeFolders = {}

    # Up to py 3.8 distutils (the one in lib as well as the one included in
    # setuptools) did its own layman's qouting of commandline parameters, that
    # had to be amended with a 'hack'. From 3.9 on quoting parameters is
    # now left to subprocess, which does the right thing.
    gentl_dir_fmt = (
        r'L"%s\\bin"'
        if sys.version_info[:2] >= (3, 9) else
        r'L\"%s\\bin\"'
        )
    DefineMacros = [
        ("UNICODE", None),
        ("_UNICODE", None),
        ("_MSC_VER", None),
        ("CAMERA_EXPORTS", None),
        ("FA_GENAPI_C_EXPORTS", None),
        ]

    ExtraCompileArgs = [
        '/Gy',      # separate functions for linker
        '/GL',      # enable link-time code generation
        '/EHsc',    # set execption handling model
        ]

    ExtraLinkArgs = [
        '/OPT:REF',     # eliminate unused functions
        '/OPT:ICF',     # eliminate identical COMDAT
        '/LTCG'         # link time code generation
        ]

    def _detect_msvc_ver(self):
        stderr = ""
        try:
            msvc = new_compiler(compiler='msvc')
            msvc.initialize()
            PIPE = subprocess.PIPE
            kw = {'stdout': PIPE, 'stderr': PIPE, 'universal_newlines': True}
            with subprocess.Popen([msvc.cc], **kw) as process:
                _, stderr = process.communicate()
        except Exception:
            pass
        m = re.search(r"\s+(\d+(?:\.\d+)+)\s+", stderr)
        return tuple(map(int, m.group(1).split('.'))) if m else (16, 0)

    def __init__(self):
        super(BuildSupportWindows, self).__init__()
        self.SwigExe = self.find_swig()
        self.SwigOptions.append("-D_WIN32")
        if get_machinewidth() != 32:
            self.SwigOptions.append("-D_WIN64")


        self.RootDevDir = os.environ.get("FAI_SDK_ROOT_PATH")
        if not self.RootDevDir:
            raise EnvironmentError("FAI_SDK_ROOT_PATH is not set")
        self.LibraryDirs = [
            os.path.join(
                self.RootDevDir,
                "lib/x64"
                )
            ]
        for inc in self.get_swig_includes():
            self.ExtraCompileArgs.append('/I%s' % inc)

        self.msvc_ver = self._detect_msvc_ver()

        if self.msvc_ver >= (19, 13):
            # add '/permissive-' to detect skipping initialization with goto
            # (available since VS 2017)
            self.ExtraCompileArgs.append('/permissive-')

    def get_swig_includes(self):
        return [os.path.join(self.RootDevDir, "include")]

    def use_debug_configuration(self):
        self.ExtraCompileArgs.append('/Od')     # disable optimizations
        self.ExtraCompileArgs.append('/Zi')     # create debug info
        self.ExtraLinkArgs.append('/DEBUG')     # create pdb file

    def find_swig(self):
        #this searches for swigwin-<version>\swig.exe at the usual places
        env_names = ['PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432']
        search = [os.environ[n] for n in env_names if n in os.environ]

        for prg in search:
            for swig_version in self.SwigVersions:
                candidate = os.path.join(
                    prg,
                    "swigwin-%s" % swig_version,
                    "swig.exe"
                    )
                if self.is_supported_swig_version(candidate):
                    info("Found swig: %s" % (candidate,))
                    return candidate

        #fallback to the standard implementation
        return BuildSupport.find_swig(self)

    def copy_runtime(self):
        super(BuildSupportWindows, self).copy_runtime()

        # detect OS and target bitness
        os_bits = 64
        if os.environ['PROCESSOR_ARCHITECTURE'] == 'x86':
            # might be WOW
            wow = os.environ.get('PROCESSOR_ARCHITEW6432', False)
            if not wow:
                os_bits = 32
        tgt_bits = get_machinewidth()

        # Copy msvc runtime
        runtime_dlls = ["vcruntime140.dll", "msvcp140.dll"]
        if tgt_bits == 64 and self.msvc_ver >= (19, 20):
            runtime_dlls.append("vcruntime140_1.dll")
        sysname = "System32" if tgt_bits == 64 or os_bits == 32 else "SysWOW64"
        sysdir = os.path.join(os.environ["windir"], sysname)
        for dll in runtime_dlls:
            src = os.path.join(sysdir, dll)
            print("Copy %s => %s" % (src, self.PackageDir))
            shutil.copy(src, self.PackageDir)


################################################################################

class BuildSupportLinux(BuildSupport):

    RootDevDir = os.getenv("FAI_SDK_ROOT_PATH", "..")

    DefineMacros = []

    print(RootDevDir)

    ExtraCompileArgs = [
        '-Wno-unknown-pragmas',
        '-fPIC',
        '-g0',
        '-Wall',
        '-O3',
        '-Wno-switch',
        ]

    ExtraLinkArgs = [
        '-g0',
        '-Wl,--enable-new-dtags',
        '-Wl,-rpath,$ORIGIN',
        ]


    RuntimeFiles = {
        "base": [
            #("libcamera_gige.so.*", ""),
            ("libfacamera.so.*", ""),
            #("libgrab_device.so.*", ""),
            #("libu3v.so.*", ""),
            ("libcamera_u3v.so.*", ""),
            ("libfa_genapi_c.so.*", ""),
            ("libimage.so.*", ""),
            #("libdevice.so.*", ""),
            #("libgenicam.so.*", ""),
            #("libnet.so.*", ""),
            ("libfacamera_c.so.*", ""),
            #("libgige_vision.so.*", ""),
            #("libos.so.*", ""),
            ],
        "genicam": [
            ("libCLAllSerial_*.so", ""),
            ("libGCBase_*.so", ""),
            ("libLog_*.so", ""),
            ("libXmlParser_*.so", ""),
            ("libCLProtocol_*.so", ""),
            ("libGenApi_*.so", ""),
            ("libMathParser_*.so", ""),
            ("libFirmwareUpdate_*.so", ""),
            ("liblog4cpp_*.so", ""),
            ("libNodeMapData_*.so", ""),
            ],
        "libpol": [
            ("liblibpol.so.2.0.0", ""),
            ],
        }

    RuntimeFolders = {}

    def __init__(self):
        super(BuildSupportLinux, self).__init__()
        self.SwigExe = self.find_swig()

        self.SwigOptions.append("-DSWIGWORDSIZE%i" % (get_machinewidth(),) )

        self.LibraryDirs = [
                self.RootDevDir,
                os.path.join(
                    self.RootDevDir,
                    "lib/x64"
                    )
                ]

        self.ExtraCompileArgs.append("-I%s" % self.RootDevDir)
        self.ExtraCompileArgs.append("-I%s" % (os.path.join(self.RootDevDir, "include")))

        self.ExtraLinkArgs.append("-L%s" % (os.path.join(self.RootDevDir, "lib/x64")))
        self.ExtraLinkArgs.append('-lrt')
        #self.ExtraLinkArgs.append('-lgige_vision')
        #self.ExtraLinkArgs.append('-lgrab_device')
        #self.ExtraLinkArgs.append('-los')
        #self.ExtraLinkArgs.append('-lu3v')
        self.ExtraLinkArgs.append('-lusb-1.0')
        self.ExtraLinkArgs.append('-lfa_genapi_c')
        self.ExtraLinkArgs.append('-lfacamera_c')
        #self.ExtraLinkArgs.append('-lcamera_gige')
        self.ExtraLinkArgs.append('-limage')
        #self.ExtraLinkArgs.append('-ldevice')
        #self.ExtraLinkArgs.append('-lgenicam')
        #self.ExtraLinkArgs.append('-lnet')
        self.ExtraLinkArgs.append('-lGCBase_gcc48_v3_4')

        print("ExtraCompileArgs:", self.ExtraCompileArgs)
        print("ExtraLinkArgs:", self.ExtraLinkArgs)
        print("LibraryDirs:", self.LibraryDirs)

    def use_debug_configuration(self):
        try:
            self.ExtraCompileArgs.remove('-O3')
        except ValueError:
            pass
        try:
            self.ExtraCompileArgs.remove('-g0')
        except ValueError:
            pass
        try:
            self.ExtraLinkArgs.remove('-g0')
        except ValueError:
            pass
        self.ExtraCompileArgs.append('-O0')
        self.ExtraCompileArgs.append('-g3')
        self.ExtraLinkArgs.append('-g3')


    def get_swig_includes(self):
        # add compiler include paths to list
        includes = [i[2:] for i in self.ExtraCompileArgs if i.startswith("-I")]
        print("include: ", includes)
        return includes

    def copy_runtime(self):
        runtime_dir = self.RootDevDir+"/lib";
        for package in self.RuntimeDefaultDeploy:
            for src, dst in self.RuntimeFiles[package]:
                full_dst = os.path.abspath(os.path.join(self.PackageDir, dst))
                if not os.path.exists(full_dst):
                    os.makedirs(full_dst)

                src = os.path.join(runtime_dir, src)
                for f in glob.glob(src):
                    print("Copy %s => %s" % (f, full_dst))
                    shutil.copy(f, full_dst)

################################################################################
################################################################################
################################################################################

if __name__ == "__main__":

    # Get a build support
    bs = BuildSupport.make()
    bs.dump()

    # Parse command line for extra arguments
    parser = argparse.ArgumentParser(
        description="Build FAI_python",
        add_help=False
        )
    parser.add_argument(
        "--pp-version",
        default=bs.get_version(),
        help="set version of packages (normally set by GIT info)"
        )
    parser.add_argument(
        "--pp-debug",
        action='store_true',
        help="build debug configuration"
        )
    parser.add_argument(
        "--swig-only",
        action='store_true',
        help="exit after swig generation"
        )
    parser.add_argument(
        "--skip-swig",
        action='store_true',
        help="skip swig to allow patching code after SWIG generated it."
        )
    parser.add_argument(
        "--rebuild-doxygen",
        action='store_true',
        help=""
        )
    parser.add_argument(
        "--generate-python-doc",
        action='store_true',
        help="generate python doc for FAI_python"
        )
    args, remainder = parser.parse_known_args()

    # re-build argv so that setup likes it...
    progname = sys.argv[0]
    sys.argv = [progname] + remainder

    # Check if help is requested...
    help_mode = False
    if "-h" in remainder or "--help" in remainder:
        help_mode = True
        parser.print_help()

    if args.pp_debug:
        bs.use_debug_configuration()
        args.pp_version += '_dbg'
    version = args.pp_version

    if "clean" in remainder:
        # Remove everything, including the "build" dir from setuptools
        print("Cleaning...")
        bs.clean("std", ["build", "FAI_python.egg-info", "dist"])
        sys.exit(0)

    if not help_mode:
        if args.rebuild_doxygen:
            print("")
            subprocess.call("python scripts/builddoxy2swig/builddoxygen.py")

    if not help_mode:
        print("Building version:", version)

    # Call swig for genicam and extensions
    if not help_mode:

        # start with fresh 'FAI_python' and 'generated' dirs if not skipping swig
        bs.clean("skip" if args.skip_swig else "keep")

        fai_python_src = bs.call_swig(
            ".",
            "FAI_python.i",
            version,
            args.skip_swig
            )
        print('\n')

        if args.swig_only:
            print("Stopping after swig...")
            sys.exit(0)

        # copy_runtime is responsible for putting all those files and directories
        # into the package directory, that need to be distributed and were not
        # placed there by 'call_swig'.
        bs.copy_runtime()
        print('\n')

    else:
        # mock to allow calling "--help" on setup
        fai_python_ext = ""

    # Define extensions
    fai_python_ext = Extension(
        'FAI_python._FAI_python',
        [fai_python_src],
        library_dirs=bs.LibraryDirs,
        libraries=["FAI_c"],
        #  define_macros=bs.DefineMacros,
        extra_compile_args=bs.ExtraCompileArgs,
        extra_link_args=bs.ExtraLinkArgs,
        )
    print("MACROS : ", bs.DefineMacros)
    print("EXTRA_COMPILE_ARGS : ", bs.ExtraCompileArgs)
    print("EXTRA_LINK_ARGS : ", bs.ExtraLinkArgs)

    #  with open("README.md", "r") as fh:
    #      long_description = fh.read()

    # While copy_runtime sets up the package directory, get_package_data_files'
    # responsibility is to express the content of that directory in a way, that
    # is understood by 'setup()'.
    package_data_files = bs.get_package_data_files()

    setup(
        name='FAI_python',
        version=version,
        author="",
        #  author_email="",
        description="The python wrapper for the FA SDK.",
        #  long_description=long_description,
        #  long_description_content_type='text/markdown',
        ext_modules=[fai_python_ext],
        packages=["FAI_python"],
        package_data={"FAI_python": package_data_files },
    )

    if args.generate_python_doc:
        print("Generating doc for python API")
        subprocess.call("python scripts/generatedoc/generatedoc.py")
