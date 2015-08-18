import os
import time

import wx
import wx.glcanvas as glcanvas

import math
import numpy as np

import OpenGL.GL as gl
import OpenGL.GL as gl
import OpenGL.arrays.vbo as gl_vbo
import OpenGL.GLU as glu

from renderer import ImmediateModeRenderer
from picker import Picker
import maproom.library.rect as rect

from ..gl.font import load_font_texture_with_alpha
from ..gl import data_types
from .. import NullPicker, BaseCanvas, int_to_color_floats

import logging
log = logging.getLogger(__name__)


class ScreenCanvas(glcanvas.GLCanvas, BaseCanvas):

    """
    The core rendering class for MapRoom app.
    """
    
    shared_context = None
    
    @classmethod
    def init_context(cls, canvas):
        # Only one GLContext is needed for the entire application -- this way,
        # textures can be shared among views.
        if cls.shared_context is None:
            cls.shared_context = glcanvas.GLContext(canvas)

    def __init__(self, *args, **kwargs):
        project = kwargs.pop('project')
        layer_manager = kwargs.pop('layer_manager')
        kwargs['attribList'] = (glcanvas.WX_GL_RGBA,
                                glcanvas.WX_GL_DOUBLEBUFFER,
                                glcanvas.WX_GL_MIN_ALPHA, 8, )

        glcanvas.GLCanvas.__init__(self, *args, **kwargs)

        self.init_context(self)
        self.is_canvas_initialized = False

        BaseCanvas.__init__(self, layer_manager, project)

        # Texture creation must be deferred until after the call to SetCurrent
        # so that the GLContext is attached to the actual window
        self.font_texture = None
        self.max_label_characters = 1000

        # Only bind paint event; others depend on window being realized
        self.Bind(wx.EVT_PAINT, self.on_draw)
        
        # mouse handler events
        self.mouse_handler = None  # defined in subclass
        
        self.native = self.get_native_control()
    
    def init_overlay(self):
        self.debug_show_bounding_boxes = False
        self.overlay = ImmediateModeRenderer(self, None)
    
    def new_picker(self):
        return Picker()

    def get_native_control(self):
        return self
    
    def set_callbacks(self):
        # Callbacks are not set immediately because they depend on the OpenGL
        # context being set on the canvas, which can't happen until the window
        # is realized.
        self.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_down)
        self.Bind(wx.EVT_MOTION, self.on_mouse_motion)
        self.Bind(wx.EVT_LEFT_UP, self.on_mouse_up)
        self.Bind(wx.EVT_RIGHT_DOWN, self.on_right_mouse_down)
        self.Bind(wx.EVT_RIGHT_UP, self.on_right_mouse_up)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_wheel_scroll)
        self.Bind(wx.EVT_ENTER_WINDOW, self.on_mouse_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_mouse_leave)
        self.Bind(wx.EVT_CHAR, self.on_key_char)
        self.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        self.Bind(wx.EVT_KEY_DOWN, self.on_key_up)
        self.Bind(wx.EVT_MENU, self.on_popup_menu)
        
        # Prevent flashing on Windows by doing nothing on an erase background event.
        ## fixme -- I think you can pass a flag to the Window instead...
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        self.Bind(wx.EVT_SIZE, self.on_resize)

    def on_draw(self, event):
        if self.native.IsShownOnScreen():
            if not self.is_canvas_initialized:
                self.SetCurrent(self.shared_context)
                
                # this has to be here because the window has to exist before creating
                # textures and making the renderer
                if self.font_texture is None:
                    self.init_font()
                    
                wx.CallAfter(self.set_callbacks)
                self.is_canvas_initialized = True
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)
            self.render()

    def on_resize(self, event):
        if not self.GetContext():
            return

        event.Skip()
        self.render(event)

    def on_mouse_down(self, event):
        # self.SetFocus() # why would it not be focused?
        mode = self.get_effective_tool_mode(event)
        self.forced_cursor = None
        self.mouse_is_down = True
        self.selection_box_is_being_defined = False
        self.mouse_down_position = event.GetPosition()
        self.mouse_move_position = self.mouse_down_position

        mode.process_mouse_down(event)
        self.set_cursor(mode)

    def on_mouse_motion(self, event):
        mode = self.get_effective_tool_mode(event)
        if self.mouse_is_down:
            mode.process_mouse_motion_down(event)
        else:
            mode.process_mouse_motion_up(event)
        self.set_cursor(mode)

    def on_mouse_up(self, event):
        mode = self.get_effective_tool_mode(event)
        self.forced_cursor = None
        mode.process_mouse_up(event)
        self.set_cursor(mode)

    def on_right_mouse_down(self, event):
        mode = self.get_effective_tool_mode(event)
        self.forced_cursor = None
        mode.process_right_mouse_down(event)
        self.set_cursor(mode)

    def on_right_mouse_up(self, event):
        mode = self.get_effective_tool_mode(event)
        self.forced_cursor = None
        mode.process_right_mouse_up(event)
        self.set_cursor(mode)

    def on_mouse_wheel_scroll(self, event):
        mode = self.get_effective_tool_mode(event)
        mode.process_mouse_wheel_scroll(event)
        self.set_cursor(mode)

    def on_mouse_enter(self, event):
        self.set_cursor()

    def on_mouse_leave(self, event):
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))
        self.mouse_handler.process_mouse_leave(event)

    def on_key_down(self, event):
        mode = self.get_effective_tool_mode(event)
        mode.process_key_down(event)
        self.set_cursor(mode)
        
        event.Skip()

    def on_key_up(self, event):
        mode = self.get_effective_tool_mode(event)
        mode.process_key_up(event)
        self.set_cursor(mode)
        
        event.Skip()

    def on_key_char(self, event):
        mode = self.get_effective_tool_mode(event)
        self.set_cursor(mode)
        
        mode.process_key_char(event)
    
    def popup_context_menu(self, event, menu):
        """Popup a simple context menu with menu items defined by the entries
        in the menu array.
        
        Each entry is a 2-tuple contining the string name and the command to
        process if the menu entry is selected.
        """
        if menu is not None:
            popup = wx.Menu()
            self.context_menu_data = dict()
            for name, cmd in menu:
                i = wx.NewId()
                popup.Append(i, name)
                self.context_menu_data[i] = cmd
            self.PopupMenu(popup, event.GetPosition())
            self.context_menu_data = None
    
    def on_popup_menu(self, event):
        cmd = self.context_menu_data[event.GetId()]
        self.project.process_command(cmd)
    
    def new_renderer(self, layer):
        r = ImmediateModeRenderer(self, layer)
        return r
    
    def load_font_texture(self):
        buffer_with_alpha, extents = load_font_texture_with_alpha()
        width = buffer_with_alpha.shape[0]
        height = buffer_with_alpha.shape[1]

        texture = gl.glGenTextures(1)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
        gl.glTexImage2D(
            gl.GL_TEXTURE_2D,
            0,
            gl.GL_RGBA8,
            width,
            height,
            0,
            gl.GL_RGBA,
            gl.GL_UNSIGNED_BYTE,
            buffer_with_alpha.tostring(),
        )
        gl.glTexParameter(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameter(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

        # gl.glBindTexture( gl.GL_TEXTURE_2D, 0 )

        return (texture, (width, height), extents)
    
    def init_font(self, max_label_characters=1000):
        (self.font_texture, self.font_texture_size, self.font_extents) = self.load_font_texture()
        self.max_label_characters = max_label_characters
        
        self.screen_vertex_data = np.zeros(
            (max_label_characters, ),
            dtype=data_types.QUAD_VERTEX_DTYPE,
        ).view(np.recarray)
        self.screen_vertex_raw = self.screen_vertex_data.view(dtype=np.float32).reshape(-1,8)
        
        self.texcoord_data = np.zeros(
            (max_label_characters, ),
            dtype=data_types.TEXTURE_COORDINATE_DTYPE,
        ).view(np.recarray)
        self.texcoord_raw = self.texcoord_data.view(dtype=np.float32).reshape(-1,8)

        # note that the data for these vbo arrays is not yet set; it is set on
        # each render and depends on the number of points being labeled
        #
        # Also note that PyOpenGL 3.1 doesn't allow VBO data to be updated
        # later when using a recarray, so force the VBO to use the raw view
        # into the recarray
        self.vbo_screen_vertexes = gl_vbo.VBO(self.screen_vertex_raw)
        self.vbo_texture_coordinates = gl_vbo.VBO(self.texcoord_raw)

    def prepare_string_texture(self, sx, sy, text): 
        # these are used just because it seems to be the fastest way to full numpy arrays
        # fixme: -- yes, but if you know how big the arrays are going to be
        #           better to build the array once. 
        screen_vertex_accumulators = [[], [], [], [], [], [], [], []]
        tex_coord_accumulators = [[], [], [], [], [], [], [], []]

        texture_width = float(self.font_texture_size[0])
        texture_height = float(self.font_texture_size[1])
        x_offset = 0
        n = 0

        for char in text:
            if char not in self.font_extents:
                char = "?"

            x = self.font_extents[char][0]
            y = self.font_extents[char][1]
            w = self.font_extents[char][2]
            h = self.font_extents[char][3]

            # again, flip y to treat point as normal screen coordinates
            screen_vertex_accumulators[0].append(sx + x_offset)
            screen_vertex_accumulators[1].append(sy - h)
            screen_vertex_accumulators[2].append(sx + x_offset)
            screen_vertex_accumulators[3].append(sy)
            screen_vertex_accumulators[4].append(sx + w + x_offset)
            screen_vertex_accumulators[5].append(sy)
            screen_vertex_accumulators[6].append(sx + w + x_offset)
            screen_vertex_accumulators[7].append(sy - h)
            x_offset += w

            tex_coord_accumulators[0].append(x / texture_width)
            tex_coord_accumulators[1].append((y + h) / texture_height)
            tex_coord_accumulators[2].append(x / texture_width)
            tex_coord_accumulators[3].append(y / texture_height)
            tex_coord_accumulators[4].append((x + w) / texture_width)
            tex_coord_accumulators[5].append(y / texture_height)
            tex_coord_accumulators[6].append((x + w) / texture_width)
            tex_coord_accumulators[7].append((y + h) / texture_height)
            n += 1

        self.screen_vertex_data.x_lb[0: n] = screen_vertex_accumulators[0]
        self.screen_vertex_data.y_lb[0: n] = screen_vertex_accumulators[1]
        self.screen_vertex_data.x_lt[0: n] = screen_vertex_accumulators[2]
        self.screen_vertex_data.y_lt[0: n] = screen_vertex_accumulators[3]
        self.screen_vertex_data.x_rt[0: n] = screen_vertex_accumulators[4]
        self.screen_vertex_data.y_rt[0: n] = screen_vertex_accumulators[5]
        self.screen_vertex_data.x_rb[0: n] = screen_vertex_accumulators[6]
        self.screen_vertex_data.y_rb[0: n] = screen_vertex_accumulators[7]

        self.texcoord_data.u_lb[0: n] = tex_coord_accumulators[0]
        self.texcoord_data.v_lb[0: n] = tex_coord_accumulators[1]
        self.texcoord_data.u_lt[0: n] = tex_coord_accumulators[2]
        self.texcoord_data.v_lt[0: n] = tex_coord_accumulators[3]
        self.texcoord_data.u_rt[0: n] = tex_coord_accumulators[4]
        self.texcoord_data.v_rt[0: n] = tex_coord_accumulators[5]
        self.texcoord_data.u_rb[0: n] = tex_coord_accumulators[6]
        self.texcoord_data.v_rb[0: n] = tex_coord_accumulators[7]

        self.vbo_screen_vertexes[0: n] = self.screen_vertex_raw[0: n]
        self.vbo_texture_coordinates[0: n] = self.texcoord_raw[0: n]
        
        return n, self.font_texture

    def prepare_string_texture_for_labels(self, values, projected_points, projected_rect): 
        r1 = projected_points[:, 0] >= projected_rect[0][0]
        r2 = projected_points[:, 0] <= projected_rect[1][0]
        r3 = projected_points[:, 1] >= projected_rect[0][1]
        r4 = projected_points[:, 1] <= projected_rect[1][1]
        mask = np.logical_and(np.logical_and(r1, r2), np.logical_and(r3, r4))
        relevant_indexes = np.where(mask)[0]
        relevant_points = projected_points[relevant_indexes]

        relevant_values = values[relevant_indexes]
        labels = map(str, relevant_values)
        n = sum(map(len, labels))

        if (n == 0 or n > self.max_label_characters):
            return 0, 0

        screen_vertex_accumulators = [[], [], [], [], [], [], [], []]
        tex_coord_accumulators = [[], [], [], [], [], [], [], []]

        texture_width = float(self.font_texture_size[0])
        texture_height = float(self.font_texture_size[1])

        for index, s in enumerate(labels):
            # determine the width of the label
            width = 0
            for c in s:
                if c not in self.font_extents:
                    c = "?"
                width += self.font_extents[c][2]
            x_offset = -width / 2

            projected_point = relevant_points[index]
            base_screen_x = (projected_point[0] - projected_rect[0][0]) / self.projected_units_per_pixel
            base_screen_y = (projected_point[1] - projected_rect[0][1]) / self.projected_units_per_pixel
            # print str( base_screen_x ) + "," + str( base_screen_y ) + "," + str( x_offset )

            for c in s:
                if c not in self.font_extents:
                    c = "?"

                x = self.font_extents[c][0]
                y = self.font_extents[c][1]
                w = self.font_extents[c][2]
                h = self.font_extents[c][3]

                # lb
                screen_vertex_accumulators[0].append(base_screen_x + x_offset)
                screen_vertex_accumulators[1].append(base_screen_y - 2 - h)
                # lt
                screen_vertex_accumulators[2].append(base_screen_x + x_offset)
                screen_vertex_accumulators[3].append(base_screen_y - 2)
                # rb
                screen_vertex_accumulators[4].append(base_screen_x + x_offset + w)
                screen_vertex_accumulators[5].append(base_screen_y - 2)
                # rt
                screen_vertex_accumulators[6].append(base_screen_x + x_offset + w)
                screen_vertex_accumulators[7].append(base_screen_y - 2 - h)

                # lb
                tex_coord_accumulators[0].append(x / texture_width)
                tex_coord_accumulators[1].append((y + h) / texture_height)
                # lt
                tex_coord_accumulators[2].append(x / texture_width)
                tex_coord_accumulators[3].append(y / texture_height)
                # rt
                tex_coord_accumulators[4].append((x + w) / texture_width)
                tex_coord_accumulators[5].append(y / texture_height)
                # rb
                tex_coord_accumulators[6].append((x + w) / texture_width)
                tex_coord_accumulators[7].append((y + h) / texture_height)

                x_offset += w

        self.screen_vertex_data.x_lb[0: n] = screen_vertex_accumulators[0]
        self.screen_vertex_data.y_lb[0: n] = screen_vertex_accumulators[1]
        self.screen_vertex_data.x_lt[0: n] = screen_vertex_accumulators[2]
        self.screen_vertex_data.y_lt[0: n] = screen_vertex_accumulators[3]
        self.screen_vertex_data.x_rt[0: n] = screen_vertex_accumulators[4]
        self.screen_vertex_data.y_rt[0: n] = screen_vertex_accumulators[5]
        self.screen_vertex_data.x_rb[0: n] = screen_vertex_accumulators[6]
        self.screen_vertex_data.y_rb[0: n] = screen_vertex_accumulators[7]

        self.texcoord_data.u_lb[0: n] = tex_coord_accumulators[0]
        self.texcoord_data.v_lb[0: n] = tex_coord_accumulators[1]
        self.texcoord_data.u_lt[0: n] = tex_coord_accumulators[2]
        self.texcoord_data.v_lt[0: n] = tex_coord_accumulators[3]
        self.texcoord_data.u_rt[0: n] = tex_coord_accumulators[4]
        self.texcoord_data.v_rt[0: n] = tex_coord_accumulators[5]
        self.texcoord_data.u_rb[0: n] = tex_coord_accumulators[6]
        self.texcoord_data.v_rb[0: n] = tex_coord_accumulators[7]

        self.vbo_screen_vertexes[0: n] = self.screen_vertex_raw[0: n]
        self.vbo_texture_coordinates[0: n] = self.texcoord_raw[0: n]
        
        return n, self.font_texture

    def prepare_screen_viewport(self):
        gl.glDisable(gl.GL_LIGHTING)
        # Don't cull polygons that are wound the wrong way.
        gl.glDisable(gl.GL_CULL_FACE)

        gl.glViewport(0, 0, self.s_w, self.s_h)
        self.set_screen_rendering_attributes()
        gl.glClearColor(1.0, 1.0, 1.0, 0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

    def set_screen_rendering_attributes(self):
        gl.glEnable(gl.GL_POINT_SMOOTH)
        gl.glEnable(gl.GL_LINE_SMOOTH)
        gl.glHint(gl.GL_LINE_SMOOTH_HINT, gl.GL_DONT_CARE)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    def prepare_picker_viewport(self):
        gl.glClearColor(1.0, 1.0, 1.0, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

    def set_picker_rendering_attributes(self):
        gl.glDisable(gl.GL_POINT_SMOOTH)
        gl.glDisable(gl.GL_LINE_SMOOTH)
        gl.glDisable(gl.GL_BLEND)

    def is_screen_ready(self):
        if not self.is_canvas_initialized:
            log.error("Render called before GLContext created")
            return False
        self.SetCurrent(self.shared_context)  # Needed every time for OS X
        return True
    
    def render_overlay(self):
        self.overlay.prepare_to_render_screen_objects()
        if self.debug_show_bounding_boxes:
            self.draw_bounding_boxes()
        self.mouse_handler.render_overlay(self.overlay)

    def draw_bounding_boxes(self):
        layers = self.layer_manager.flatten()
        for layer in layers:
            w_r = layer.bounds
            if (w_r != rect.EMPTY_RECT) and (w_r != rect.NONE_RECT):
                s_r = self.get_screen_rect_from_world_rect(w_r)
                r, g, b, a = int_to_color_floats(layer.style.line_color)
                self.overlay.draw_screen_box(s_r, r, g, b, 0.5, stipple_pattern=0xf0f0)

    def post_render_update_ui_hook(self, elapsed, event):
        self.SwapBuffers()

        def update_status(message):
            self.project.task.status_bar.debug = message
        wx.CallAfter(update_status, "Render complete, took %f seconds." % elapsed)

        if (event is not None):
            event.Skip()

    # functions related to world coordinates, projected coordinates, and screen coordinates

    def get_screen_size(self):
        return self.native.GetClientSize()

    def get_canvas_as_image(self):
        window_size = self.get_screen_size()

        gl.glReadBuffer(gl.GL_FRONT)

        raw_data = gl.glReadPixels(
            x=0,
            y=0,
            width=window_size[0],
            height=window_size[1],
            format=gl.GL_RGB,
            type=gl.GL_UNSIGNED_BYTE,
            outputType=str,
        )

        bitmap = wx.BitmapFromBuffer(
            width=window_size[0],
            height=window_size[1],
            dataBuffer=raw_data,
        )

        image = wx.ImageFromBitmap(bitmap)

        # Flip the image vertically, because glReadPixel()'s y origin is at
        # the bottom and wxPython's y origin is at the top.
        screenshot = image.Mirror(horizontally=False)
        return screenshot