# -*- coding: utf-8 -*-
# vispy: testskip
# Copyright (c) 2014, Vispy Development Team.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.
"""
Orthographic projection
"""

import wx
import math
import numpy as np

from vispy import app, gloo
from vispy.gloo import Program, VertexBuffer, IndexBuffer
from vispy.util.transforms import ortho, translate, rotate
from vispy.geometry import create_cube

vertex = """
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;
uniform vec4 u_color;

attribute vec3 position;
attribute vec4 color;

varying vec4 v_color;
void main()
{
    v_color = u_color * color;
    gl_Position = u_projection * u_view * u_model * vec4(position,1.0);
}
"""

vertex_type = [
    ('position', np.float32, 3),
    ('color', np.float32, 4)]

xy_depth_type = [
    ('xy', np.float32, 2),
    ('depth', np.float32, 1),
    ('color', np.float32, 4)]

fragment = """
varying vec4 v_color;
void main()
{
    gl_FragColor = v_color;
}
"""


class Canvas(app.Canvas):
    def __init__(self, *args, **kwargs):
        app.Canvas.__init__(self, *args, **kwargs)

    def on_initialize(self, event):
        # Build cube data
        V, I, O = create_cube()
        # Each item in the vertex data V is a tuple of lists, e.g.:
        #
        # ([1.0, 1.0, 1.0], [0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 1.0, 1.0])
        #
        # where each list corresponds to one of the attributes in the vertex
        # shader.  (See vispy.geometry.create_cube).  To experiment with this,
        # I've removed the 2nd tuple (the texcoord) and changed the vertex
        # shader from vispy5.  We'll see if this works. UPDATE: yes, it does!
        v = np.zeros(4, vertex_type)
        v['position'] = [
            [-8905559.0, 1221705.625, 1.0],
            [-6928748.0, 1424595.625, 1.0],
            [-4619759.0, 1455235.25, 1.0],
            [-3227152.0, 1314223.25, 1.0],
            ]
        print v
        faces = [0, 1, 2, 1, 2, 3]
        outline = [0, 1, 1, 2, 2, 3, 3, 0]
        self.vertices = VertexBuffer(v)
        self.faces = IndexBuffer(faces)
        self.outline = IndexBuffer(outline)

        # Build program
        # --------------------------------------
        self.program = Program(vertex, fragment)
        self.program.bind(self.vertices)

        # Build view, model, projection & normal
        # --------------------------------------
        view = np.eye(4, dtype=np.float32)
        model = np.eye(4, dtype=np.float32)
        translate(view, 0, 0, -5)
        self.program['u_model'] = model
        self.program['u_view'] = view
 
        # OpenGL initalization
        # --------------------------------------
        gloo.set_state(clear_color=(1.0, 1.0, 1.0, 1.00), depth_test=True,
                       polygon_offset=(1, 1), line_width=0.75,
                       blend_func=('src_alpha', 'one_minus_src_alpha'))

    def on_draw(self, event):
        gloo.clear(color=True, depth=True)

        # Filled cube
        gloo.set_state(blend=False, depth_test=True, polygon_offset_fill=True)
#        self.program['u_color'] = 1, 1, 1, 1
#        self.program.draw('triangles', self.faces)
#
#        # Outlined cube
#        gloo.set_state(blend=True, depth_mask=True, polygon_offset_fill=False)
        self.program['u_color'] = 1, 0, 0, 1
        self.program.draw('lines', self.outline)

        gloo.set_state(depth_mask=True)

    def on_resize(self, event):
        gloo.set_viewport(0, 0, *event.size)
        projection = ortho(-9000000, -3000000, 1000000, 1500000, 0.5, 1000.0)
        self.program['u_projection'] = projection
        print projection

class TestFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, -1, "Vispy Test",
                          wx.DefaultPosition, size=(500, 500))

        MenuBar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(-1, "New Window")
        self.Bind(wx.EVT_MENU, self.on_new_window)
        file_menu.Append(wx.ID_EXIT, "&Quit")
        self.Bind(wx.EVT_MENU, self.on_quit, id=wx.ID_EXIT)
        MenuBar.Append(file_menu, "&File")
        self.SetMenuBar(MenuBar)

        self.canvas = Canvas(app="wx", parent=self)
        native = self.canvas.native
        native.Show()
        
        native.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_down)
#        native.Bind(wx.EVT_MOTION, self.on_mouse_motion)
#        native.Bind(wx.EVT_LEFT_UP, self.on_mouse_up)
#        native.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_wheel_scroll)
#        native.Bind(wx.EVT_ENTER_WINDOW, self.on_mouse_enter)
#        native.Bind(wx.EVT_LEAVE_WINDOW, self.on_mouse_leave)
#        native.Bind(wx.EVT_CHAR, self.on_key_char)
#        native.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
#        native.Bind(wx.EVT_KEY_DOWN, self.on_key_up)

    def on_mouse_down(self, event):
        # self.SetFocus() # why would it not be focused?
        print("in on_mouse_down: event=%s" % event)
        event.Skip()

    def on_new_window(self, event):
        frame = TestFrame()
        frame.Show(True)

    def on_quit(self, event):
        app.quit()

if __name__ == '__main__':
    myapp = wx.App(0)
    frame = TestFrame()
    frame.Show(True)
    app.run()
