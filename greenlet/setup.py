#!/usr/bin/env python

import sys
import subprocess
from setuptools import setup, find_packages, Extension
from glob import glob
import os
import pyproj
import maproom.Version as Version


# Definintion of compiled extension code:
import numpy # so it can find the headers
file_scanner = Extension(
    "maproomlib.utility.file_scanner",
    sources = [ "maproomlib/utility/file_scanner_src/file_scan_module.c" ],
    include_dirs = [ numpy.get_include() ],
)
bitmap = Extension(
    "maproomlib.utility.Bitmap",
    sources = [ "maproomlib/utility/Bitmap.pyx" ],
    include_dirs = [ numpy.get_include() ],
)
shape = Extension(
    "maproomlib.utility.Shape",
    sources = [ "maproomlib/utility/Shape.pyx" ],
    include_dirs = [ numpy.get_include() ],
)
cntr = Extension(
    "maproomlib.utility.cntr",
    sources = [ "maproomlib/utility/cntr.c" ],
    include_dirs = [ numpy.get_include() ],
)
contour = Extension(
    "maproomlib.utility.Contour",
    sources = [ "maproomlib/utility/Contour.pyx" ],
    include_dirs = [ numpy.get_include() ],
)

gl_include_dirs = [ numpy.get_include() ]
gl_library_dirs = []
gl_libraries = [ "GL", "GLU" ]

if sys.platform.startswith( "win" ):
    gl_libraries = [ "opengl32", "glu32" ]
elif sys.platform == "darwin":
    gl_include_dirs.append(
        "/System/Library/Frameworks/OpenGL.framework/Headers", 
    )
    gl_library_dirs.append(
        "/System/Library/Frameworks/OpenGL.framework/Libraries",
    )

tessellator = Extension(
    "maproomlib.plugin.Opengl_renderer.Tessellator",
    sources = [ "maproomlib/plugin/Opengl_renderer/Tessellator.pyx" ],
    include_dirs = gl_include_dirs,
    library_dirs = gl_library_dirs,
    libraries = gl_libraries,
)
render = Extension(
    "maproomlib.plugin.Opengl_renderer.Render",
    sources = [ "maproomlib/plugin/Opengl_renderer/Render.pyx" ],
    include_dirs = gl_include_dirs,
    library_dirs = gl_library_dirs,
    libraries = gl_libraries,
)
ext_modules = [ file_scanner, bitmap, shape, cntr, contour, tessellator, render ]


if sys.platform.startswith( "win" ) and "py2exe" in sys.argv:
    import py2exe

    # Help py2exe find MSVCP90.DLL
    sys.path.append( "c:/Program Files (x86)/Microsoft Visual Studio 9.0/VC/redist/x86/Microsoft.VC90.CRT" )


# Make pyproj's data into a resource instead of including it in the zip file
# so pyproj can actually find it. (Note: It's actually still included in the zip
# file.)
pyproj_data = glob(
    os.path.join(
        os.path.dirname( pyproj.__file__ ),
        "data", "*",
    )
)


# Determine the current svn revision, if this is an svn checkout. Also, make
# sure we don't have any local modifications.
try:
    output = subprocess.Popen(
        [ "svn", "info" ], stdout = subprocess.PIPE,
    ).communicate()[ 0 ]

    for line in output.split( "\n" ):
        if line.startswith( "Revision: " ):
            svn_revision = int( line.split( ": " )[ 1 ] )
            break
    else:
        svn_revision = None

    if "py2app" in sys.argv or "py2exe" in sys.argv:
        output = subprocess.Popen(
            [ "svn", "stat", "-q" ], stdout = subprocess.PIPE,
        ).communicate()[ 0 ]
        if len( output.strip() ) > 0:
            # Yes, this is obnoxious. But it prevents accidentally releasing
            # software with local modifications.
            print "Local modifications exist. Refusing to build an installer."
            print "Please check in or revert your changes before building."
            sys.exit( 1 )

except ( OSError, ValueError, IndexError ):
    svn_revision = None


# Poke the revision into Maproom's version info file so that the packaged
# application knows what svn revision it's built from. This can make debugging
# a whole lot easier.
VERSION_FILENAME = "maproom/Version.py"
if svn_revision:
    lines = open( VERSION_FILENAME ).readlines()
    os.rename( VERSION_FILENAME, "%s.orig" % VERSION_FILENAME )
    version_file = open( VERSION_FILENAME, "w" )

    for line in lines:
        if line.startswith( "SOURCE_CONTROL_REVISION=" ):
            version_file.write( 'SOURCE_CONTROL_REVISION="%d"' % svn_revision )
        else:
            version_file.write( line )

    version_file.close()


data_files = [
    ( "maproomlib", glob( "maproomlib/*.txt" ) ),
    ( "maproomlib/ui/images", glob( "maproomlib/ui/images/*.png" ) ),
    ( "maproom", glob( "maproom/*.txt" ) ),
    ( "maproom/ui/images",
        glob( "maproom/ui/images/*.ico" ) +
        glob( "maproom/ui/images/*.png" )
    ),
    ( "maproom/ui/images/toolbar",
        glob( "maproom/ui/images/toolbar/*.png" )
    ),
    ( "maproom/ui/images/cursors",
        glob( "maproom/ui/images/cursors/*.ico" )
    ),
    ( "pyproj_data", pyproj_data ),
]


if sys.platform.startswith( "win" ) and "py2exe" in sys.argv:
    # Add missing DLL files that py2exe doesn't pull in automatically.
    data_files.append(
        ( ".", [ "..\..\PROJ.4\workspace\src\proj.dll" ] ),
    )


common_includes = [
    "ctypes", "ctypes.util", "greenlet",
]

py2app_includes = [
    "OpenGL_accelerate",
    "OpenGL_accelerate.formathandler",
]


try:
    setup(
        name = "Maproom",
        version = "1.0",
        description = "High-performance 2d mapping",
        author = "NOAA",
        data_files = data_files,
        packages = find_packages(),
        ext_modules = ext_modules,
        app = [ "maproom/maproom.py" ],
        windows = [ dict(
            script = "maproom/maproom.py",
            icon_resources = [ ( 1, "maproom/ui/images/maproom.ico" ) ],
        ) ],
        options = dict(
            py2app = dict(
                argv_emulation = True,
                optimize = 2, # Equivalent to running "python -OO".
                semi_standalone = False,
                includes = common_includes + py2app_includes,
                iconfile = "maproom/ui/images/maproom.icns",
                plist = dict(
                    CFBundleName = "Maproom",
                    CFBundleTypeExtensions = [ "verdat", "kap", "bna" ],
                    CFBundleTypeName = "Geographic Document",
                    CFBundleTypeRole = "Editor",
                    CFBundleShortVersionString = Version.VERSION,
                    CFBundleGetInfoString = "Maproom %s" % Version.VERSION,
                    CFBundleExecutable = "Maproom",
                    CFBUndleIdentifier = "gov.noaa.maproom", 
                )
            ),
            py2exe = dict(
                optimize = 2,
                # See http://www.py2exe.org/index.cgi/PyOpenGL
                # and http://www.py2exe.org/index.cgi/TkInter
                includes = common_includes,
                excludes = [
                    "OpenGL", "Tkconstants", "Tkinter", "tcl", "_imagingtk",
                    "PIL._imagingtk", "ImageTk", "PIL.ImageTk", "FixTk",
                ],
            ),
            build = dict(
                #compiler = "mingw32",
                compiler = "msvc",
            ) if sys.platform.startswith( "win" ) else {},
        )
    )

    if sys.platform.startswith( "win" ) and "py2exe" in sys.argv:
        try:
            import triangle
            import shutil
            print "*** copy Triangle module ***"
            triangle_path = triangle.__file__
            try:
                shutil.copy( triangle_path, "dist" )
            except ( OSError, WindowsError ), error:
                if not "already exists" in str( error ):
                    raise
        except ImportError:
            pass

    if sys.platform.startswith( "win" ) and "py2exe" in sys.argv:
        # See http://www.py2exe.org/index.cgi/PyOpenGL
        import OpenGL
        import OpenGL_accelerate
        import shutil
        print "*** copy PyOpenGL module ***"
        opengl_dir = os.path.dirname( OpenGL.__file__ )
        opengl_accelerate_dir = os.path.dirname( OpenGL_accelerate.__file__ )
        try:
            shutil.copytree(
                opengl_dir, os.path.join( "dist", "OpenGL" ),
                ignore = shutil.ignore_patterns( "GLUT", "Tk" ),
            )
            shutil.copytree(
                opengl_accelerate_dir,
                os.path.join( "dist", "OpenGL_accelerate" ),
            )
        except WindowsError, error:
            if not "already exists" in str( error ):
                raise

        print "*** create installer ***"
        if svn_revision:
            full_version = "%s (r%s)" % ( Version.VERSION, svn_revision )
            spaceless_version = "%s_r%s" % \
                ( Version.VERSION.replace( " ", "_" ), svn_revision )
        else:
            full_version = Version.VERSION
            spaceless_version = Version.VERSION.replace( " ", "_" )

        iss_filename = "dist\\maproom.iss"
        iss_file = open( iss_filename, "w" )
        iss_file.write( """
[Setup]
AppId={{8AE5A4C3-B67E-4243-9F45-401C554A9019}
AppName=Maproom
AppVerName=Maproom %s
AppPublisher=NOAA
AppPublisherURL=http://www.noaa.gov/
AppSupportURL=http://www.noaa.gov/
AppUpdatesURL=http://www.noaa.gov/
DefaultDirName={pf}\Maproom
DefaultGroupName=Maproom
OutputBaseFilename=Maproom_%s
SetupIconFile=..\maproom\ui\images\maproom.ico
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "maproom.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\Maproom"; Filename: "{app}\maproom.exe"
Name: "{commondesktop}\Maproom"; Filename: "{app}\maproom.exe"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\Maproom"; Filename: "{app}\maproom.exe"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\maproom.exe"; Description: "{cm:LaunchProgram,Maproom}"; Flags: nowait postinstall skipifsilent
""" % ( full_version, spaceless_version ) )
        iss_file.close()

        import shutil
        shutil.rmtree( "dist\\Output", ignore_errors = True )

        os.system(
            '"C:\Program Files (x86)\Inno Setup 5\ISCC.exe" %s' % iss_filename,
        )


finally:
    if svn_revision:
        os.remove( VERSION_FILENAME )
        os.rename( "%s.orig" % VERSION_FILENAME, VERSION_FILENAME )