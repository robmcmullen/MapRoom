import os
import os.path
import sys
import math
import wx
import argparse
from wx.lib.pubsub import pub

#import wx.glcanvas as glcanvas
#import pyproj
from ui.Menu_bar import Menu_bar
from ui.Tool_bar import Tool_bar
from ui.Properties_panel import Properties_panel
from ui.Triangle_dialog import Triangle_dialog
from ui.Merge_layers_dialog import Merge_layers_dialog
from ui.Merge_duplicate_points_dialog import Merge_duplicate_points_dialog
import ui.File_opener
import Layer_manager
import Layer_tree_control
import Editor
#import lon_lat_grid
#import library.Opengl_renderer
#import library.rect as rect
import app_globals
import preferences

from MapController import MapController
from ui.RenderWindow import RenderWindow

"""
    maproom to-do list (June 24, 2011)
    
    - finish panel items in Editor
    - save layer to .mrv file (using xml)
    - read layer from .mrv file
    - triangulation (basic workflow; just adds triangle objects to current layer)
    - read le file into multi-layer file
    - contouring (basic workflow; just adds polygons to current layer)
    - merge verdat points (and lines?) between to layers into a new layer
    - remove duplicate points in layer (within tolerance)
     
    - delete layer    
    - create new layer
"""


class Application(wx.App):

    """
    The UI for the Maproom application.
    """

    NAME = "Maproom"

    current_map = None
    frame = None
    maps = []

    def __init__(self):
        print "in application.__init__"
        app_globals.application = self
        wx.App.__init__(self, False)

    def OnInit(self):
        print "in application.OnInit"
        self.SetAppName(self.NAME)

        self.process_args()
        
        self.setup_pubsub()
        self.setup_filehistory()

        self.new_map()
        
        self.load_initial_files()
        
        self.is_initialized = True

        return True
    
    def process_args(self):
        parser = argparse.ArgumentParser(description="NOAA mapping utility")
        parser.add_argument("files", nargs="*", help="Open supported image/vector/map files")
        self.args = parser.parse_args()

        data_dir = wx.StandardPaths.Get().GetUserDataDir()
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        app_globals.preferences = preferences.MaproomPreferences(os.path.join(data_dir, "MaproomPrefs.json"))
    
    def load_initial_files(self):
        for filename in self.args.files:
            print "opening:", filename
            ui.File_opener.open_file(filename)
    
    def setup_pubsub(self):
        pub.subscribe(self.on_recent_files_config, ('recent_files', 'config'))
        pub.subscribe(self.on_recent_files_update, ('recent_files', 'update'))
        pub.subscribe(self.on_recent_files_open, ('recent_files', 'open'))
    
    def setup_filehistory(self):
        configfile = os.path.join(wx.StandardPaths.Get().GetUserDataDir(), "config.dat")
        self.config = wx.Config(self.NAME, style=wx.CONFIG_USE_LOCAL_FILE, localFilename=configfile)
        print self.config
        self.filehistory = wx.FileHistory(app_globals.preferences["Number of Recent Files"])
        self.filehistory.Load(self.config)

    def on_recent_files_config(self, menu):
        #config = self.get_config_file("recent-files.dat")
        self.filehistory.UseMenu(menu)
        self.filehistory.AddFilesToMenu()
    
    def on_recent_files_update(self, path):
        print "recent_files_update:", path
        self.filehistory.AddFileToHistory(path)
        self.filehistory.Save(self.config)
        self.config.Flush()

    def on_recent_files_open(self, index):
        path = self.filehistory.GetHistoryFile(index)
        print "recent_files_open:", path
        ui.File_opener.open_file(path)

    def new_map(self):
        map = MapController()
        self.maps.append(map)
        map.show_frame()
        self.set_current_map(map)

    def set_current_map(self, map):
        self.current_map = map

        # TODO: Remove the following couplings

        # this is mostly used to provide a parent control for dialogs and for frame.GetIcon() access
        # we may be able to replace this with wx.GetApp().GetTopWindow(), so long as we
        # ensure the current frame is always set to the top window.
        self.frame = self.current_map.frame
        self.SetTopWindow(self.frame)

        # this is pretty much so that Layer can directly access the renderer when rendering
        # itself. We should be able to remove this once we move layer rendering logic into
        # rendering-specific classes.
        self.renderer = self.current_map.renderer

        # for its get_selected_layer and select_layer methods
        self.layer_tree_control = self.current_map.layer_tree_control

    def refresh(self, rebuild_tree=False):
        """
        TODO: This needs to be removed, but it will take a while since this has calls everywhere,
        so for now we just leave it and have it do the best thing possible.
        """
        if self.current_map is not None:
            self.current_map.refresh(None, rebuild_tree)

    def MacReopenApp(self):
        """
        Invoked by wx when the Maproom dock icon is clicked on Mac OS X.
        """
        self.GetTopWindow().Raise()

    def MacOpenFile(self, filename):
        """
        Invoked by wx when a file is dropped on the Maproom dock icon on Mac OS X.
        """
        # FIXME: for some reason, when using python on the command line this
        # method gets called for each argument, including the "maproom.py"
        # argument
        if not hasattr(sys, "frozen"):
            if filename in sys.argv:
                print "MacOpenFile: found %s in sys.argv! Ignoring!" % filename
                index = sys.argv.index(filename)
                del sys.argv[index]
                return
        ui.File_opener.open_file(filename)

    def OnExit(self):
        self.is_closing = True
        app_globals.layer_manager.destroy()
        app_globals.preferences.save()
