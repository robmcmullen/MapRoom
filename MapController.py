import os
import os.path
import sys
import math
import wx
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

class MapController( object ):
    """
    Manages the UI and data objects, such as layers, for a map.
    """
    DEFAULT_FRAME_SIZE = ( 1000, 750 )
    LEFT_SASH_POSITION = 200
    TOP_SASH_POSITION = 250
    IMAGE_PATH = "ui/images"
    ICON_FILENAME = os.path.join( IMAGE_PATH, "maproom.ico" )
    
    NAME = "Maproom"
    
    MODE_PAN = 0
    MODE_ZOOM_RECT = 1
    MODE_EDIT_POINTS = 2
    MODE_EDIT_LINES = 3
    
    frame = None
    menu_bar = None
    tool_bar = None
    renderer_splitter = None
    properties_splitter = None
    renderer = None # the glcanvas
    layer_tree_panel = None
    properties_panel = None
    layer_tree_control = None
    layer_manager = None
    status_bar = None
    
    mode = MODE_PAN
    hand_cursor = None
    hand_closed_cursor = None
    forced_cursor = None
    
    lon_lat_grid = None
    lon_lat_grid_shown = True
    
    is_alt_key_down = False
    selection_box_is_being_defined = False;
    
    is_initialized = False
    is_closing = False
    
    def __init__( self ):
        print "Initializing new Map"
        self.layer_manager = Layer_manager.Layer_manager()
        self.editor = Editor.Editor(self.layer_manager)
        
        # a hack until we remove the coupling of globals to this object's members
        self.bind_globals()
    
        self.frame = wx.Frame( None, wx.ID_ANY, self.NAME )
        self.frame.SetIcon( wx.Icon( self.ICON_FILENAME, wx.BITMAP_TYPE_ICO ) )
        self.frame.SetSizeHints( 250, 250 )
        
        pos = self.frame.Position
        for tlw in wx.GetTopLevelWindows():
            if not tlw is self.frame and isinstance(tlw, wx.Frame):
                if tlw.Position.x == pos.x:
                    pos.x += 20
                if tlw.Position.y == pos.y:
                    pos.y += 20
        self.frame.Move(pos)
        
        self.renderer_splitter = wx.SplitterWindow(
            self.frame,
            wx.ID_ANY,
            style = wx.SP_3DSASH,
        )
        self.renderer_splitter.SetMinimumPaneSize( 20 )
        
        self.properties_splitter = wx.SplitterWindow(
            self.renderer_splitter,
            wx.ID_ANY,
            style = wx.SP_3DSASH,
        )
        self.properties_splitter.SetMinimumPaneSize( 20 )
        
        self.menu_bar = Menu_bar( self )
        self.frame.SetMenuBar( self.menu_bar )
        
        self.tool_bar = Tool_bar( self )
        self.frame.SetToolBar( self.tool_bar )
        # On Mac, we need to call Realize after setting the frame's toolbar.
        self.tool_bar.Realize()
        
        self.status_bar = self.frame.CreateStatusBar()
        
        print "Initializing RenderWindow..."
        self.renderer = RenderWindow( self.renderer_splitter)

        self.renderer_splitter.SplitVertically(
            self.properties_splitter,
            self.renderer,
            self.LEFT_SASH_POSITION,
        )
        
        self.layer_tree_control = Layer_tree_control.Layer_tree_control( self.properties_splitter )
        self.properties_panel = Properties_panel( self.properties_splitter )
        
        self.properties_splitter.SplitHorizontally(
            self.layer_tree_control,
            self.properties_panel,
            self.TOP_SASH_POSITION,
        )
        
        # TODO: Make a frame delegate for these parts
        self.frame.Bind( wx.EVT_CLOSE, self.close )
        self.frame.Bind( wx.EVT_MENU, self.close_app, id = wx.ID_EXIT )
        self.frame.Bind( wx.EVT_ACTIVATE, self.activate )
        self.frame.Bind( wx.EVT_ACTIVATE_APP, self.refresh )

        pub.subscribe(self.on_layer_inserted, ('layer', 'inserted'))
        pub.subscribe(self.on_layer_selection_changed, ('layer', 'selection', 'changed'))

        self.renderer.SetFocus()
        
        self.frame.SetSize( self.DEFAULT_FRAME_SIZE )
        self.frame.Show( True )
        self.is_initialized = True
    
    def activate( self, event ):
        if event.Active:
            print "setting this as the active frame"
            self.bind_globals()
            self.refresh()
    
    def bind_globals( self ):
        # TODO: remove this coupling
        app_globals.application.set_current_map(self)
        app_globals.layer_manager = self.layer_manager
        app_globals.editor = self.editor
    
    def show_frame( self ):
        self.frame.Show( True )
        self.renderer.SetFocus()
    
    def on_layer_selection_changed( self, manager, layer ):
        if self.layer_manager == manager:
            self.menu_bar.enable_disable_menu_items()
            self.tool_bar.enable_disable_tools()
            self.refresh()
    
    def on_layer_inserted( self, manager, layer ):
        if self.layer_manager == manager:
            self.refresh( None, True )
            self.layer_tree_control.select_layer( layer )
    
    def show_triangle_dialog_box( self ):
        self.show_dialog_of_type(Triangle_dialog)
    
    def show_merge_layers_dialog_box( self ):
        Merge_layers_dialog().show()
    
    def show_dialog_of_type( self, type ):
        """
        This will look for an existing dialog of type, and will Raise it if found,
        otherwise it will create the dialog and show it. This should probably go into
        some utility function somewhere.
        """
        name = type.NAME
        dialog = None
        for window in wx.GetTopLevelWindows():
            if window.Name == name:
                dialog = window
                break
                
        if dialog:
            dialog.Raise()
        else:
            dialog = type()
            dialog.Show()
        dialog.SetFocus()
    
    def show_merge_duplicate_points_dialog_box( self ):
        self.show_dialog_of_type(Merge_duplicate_points_dialog)
    
    def close( self, event ):
        self.is_closing = True
        self.frame.Destroy()
        
    def close_app( self, event ):
        wx.GetApp().ExitMainLoop()
    
    def refresh( self, event = None, rebuild_layer_tree_control = False ):
        print "refresh called"
        ## fixme: this shouldn't be required!
        if ( self.is_closing ):
            return
        
        if ( rebuild_layer_tree_control and self.layer_tree_control != None ):
            self.layer_tree_control.rebuild()
        if self.renderer is not None:
        #    self.renderer.render()
            # On Mac this is neither necessary nor desired.
            if not sys.platform.startswith('darwin'):
                self.renderer.Update()
            self.renderer.Refresh()
        if ( self.layer_tree_control != None and self.properties_panel != None ):
            layer = self.layer_tree_control.get_selected_layer()
            # note that the following call only does work if the properties for the layer have changed
            self.properties_panel.display_panel_for_layer( layer )
        if ( self.is_initialized ):
            self.menu_bar.enable_disable_menu_items()
            self.tool_bar.enable_disable_tools()