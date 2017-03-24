import os
import cgi

import wx
from wx.lib.ClickableHtmlWindow import PyClickableHtmlWindow

# Enthought library imports.

from omnivore.framework.panes import FrameworkPane
from omnivore.utils.wx.springtabs import SpringTabs
from omnivore.utils.wx.download_manager import DownloadControl

from layer_tree_control import LayerTreeControl
from ui.info_panels import LayerInfoPanel, SelectionInfoPanel
from ui.triangle_panel import TrianglePanel
from ui.merge_panel import MergePointsPanel
from ui.undo_panel import UndoHistoryPanel

import logging
log = logging.getLogger(__name__)


class LayerSelectionPane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.layer_selection_pane'
    name = 'Layers'

    def create_contents(self, parent):
        control = LayerTreeControl(parent, self.task.active_editor, size=(200, 300))
        return control


class LayerInfoPane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.layer_info_pane'
    name = 'Current Layer'

    def create_contents(self, parent):
        control = LayerInfoPanel(parent, self.task.active_editor, size=(200, 200))
        return control


class SelectionInfoPane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.selection_info_pane'
    name = 'Current Selection'

    def create_contents(self, parent):
        control = SelectionInfoPanel(parent, self.task.active_editor, size=(200, 200))
        return control


class TriangulatePane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.triangulate_pane'
    name = 'Triangulate'

    def create_contents(self, parent):
        control = TrianglePanel(parent, self.task)
        return control


class MergePointsPane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.merge_points_pane'
    name = 'Merge Points'

    def create_contents(self, parent):
        control = MergePointsPanel(parent, self.task)
        return control


class UndoHistoryPane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.undo_history_pane'
    name = 'Undo History'

    def create_contents(self, parent):
        control = UndoHistoryPanel(parent, self.task)
        return control

    # trait change handlers

    def _task_changed(self):
        log.debug("TASK CHANGED IN UNDOHISTORYPANE!!!! %s" % self.task)
        if self.control:
            self.control.set_task(self.task)


# class FlaggedPointPanel(wx.Panel):
#    def __init__(self, parent, task, **kwargs):
#        self.task = task
#        self.editor = None
#        wx.Panel.__init__(self, parent, wx.ID_ANY, **kwargs)
#
#        # Mac/Win needs this, otherwise background color is black
#        attr = self.GetDefaultAttributes()
#        self.SetBackgroundColour(attr.colBg)
#
#        self.sizer = wx.BoxSizer(wx.VERTICAL)
#
#        self.points = wx.ListBox(self, size=(100, -1))
#
#        self.sizer.Add(self.points, 1, wx.EXPAND)
#
#        self.SetSizer(self.sizer)
#        self.sizer.Layout()
#        self.Fit()

class FlaggedPointPanel(wx.ListBox):
    def __init__(self, parent, task, **kwargs):
        self.task = task
        self.editor = None
        self.point_indexes = []
        wx.ListBox.__init__(self, parent, wx.ID_ANY, **kwargs)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_click)

        # Return key not sent through to EVT_CHAR, EVT_CHAR_HOOK or
        # EVT_KEY_DOWN events in a ListBox. This is the only event handler
        # that catches a Return.
        self.Bind(wx.EVT_KEY_UP, self.on_char)

    def DoGetBestSize(self):
        """ Base class virtual method for sizer use to get the best size
        """
        width = 100
        height = -1
        best = wx.Size(width, height)

        # Cache the best size so it doesn't need to be calculated again,
        # at least until some properties of the window change
        self.CacheBestSize(best)

        return best

    def on_char(self, evt):
        keycode = evt.GetKeyCode()
        log.debug("key down: %s" % keycode)
        if keycode == wx.WXK_RETURN:
            index = self.GetSelection()
            self.process_index(index)
        evt.Skip()

    def on_click(self, evt):
        index = self.HitTest(evt.GetPosition())
        if index >= 0:
            self.Select(index)
            self.process_index(index)

    def process_index(self, index):
        point_index = self.point_indexes[index]
        editor = self.task.active_editor
        layer = editor.layer_tree_control.get_selected_layer()
        print point_index, layer
        editor.layer_canvas.do_center_on_point_index(layer, point_index)

    def set_flagged(self, point_indexes):
        self.point_indexes = list(point_indexes)
        self.Set([str(i) for i in point_indexes])

    def recalc_view(self):
        editor = self.task.active_editor
        if editor is not None:
            self.editor = editor
            layer = editor.layer_tree_control.get_selected_layer()
            try:
                points = layer.get_flagged_point_indexes()
            except AttributeError:
                points = []
            self.set_flagged(points)

    def refresh_view(self):
        editor = self.task.active_editor
        if editor is not None:
            if self.editor != editor:
                self.recalc_view()
            else:
                self.Refresh()

    def activateSpringTab(self):
        self.recalc_view()

    def get_notification_count(self):
        self.recalc_view()
        return len(self.point_indexes)


class DownloadPanel(DownloadControl):
    def __init__(self, parent, task, **kwargs):
        self.task = task
        self.editor = None
        downloader = self.task.window.application.get_downloader()
        DownloadControl.__init__(self, parent, downloader, size=(400, -1), **kwargs)

    # turn the superclass attribute path into a property so we can override it
    # and pull out the paths from the preferences
    @property
    def path(self):
        prefs = self.task.get_preferences()
        if prefs.download_directory:
            return prefs.download_directory
        return os.getcwd()

    @path.setter
    def path(self, value):
        if value:
            prefs = self.task.get_preferences()
            prefs.download_directory = value

    def refresh_view(self):
        self.Refresh()

    def activateSpringTab(self):
        self.refresh_view()

    def get_notification_count(self):
        self.refresh_view()
        return self.num_active


class SidebarPane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.sidebar'
    name = 'Sidebar'

    movable = False
    caption_visible = False
    dock_layer = 9

    def flagged_cb(self, parent, task, **kwargs):
        control = FlaggedPointPanel(parent, task)

    def download_cb(self, parent, task, **kwargs):
        self.download_control = DownloadPanel(parent, task)

    def create_contents(self, parent):
        control = SpringTabs(parent, self.task, popup_direction="left")
        control.addTab("Flagged Points", self.flagged_cb)
        control.addTab("Downloads", self.download_cb)
        return control

    def refresh_active(self):
        self.control.update_notifications()
        active = self.control._radio
        if active is not None and active.is_shown:
            active.managed_window.refresh_view()


class HtmlHelpPane(FrameworkPane):
    #### TaskPane interface ###################################################

    id = 'maproom.html_help_pane'
    name = 'HTML Help'
    code_header = "Markup"
    desc_header = "Appearance"
    help_text = """<h1>Title</h1>|<h1>Title</h1>
    <h2>Section</h2>|<h2>Section</h2>
    <h3>Subsection</h3>|<h3>Subsection</h3>
    <p>|start new paragraph
    <i>italics</i>|<i>italics</i>
    <b>bold</b>|<b>bold</b>
    <ul>|start list
    <li>list item|<ul><li>list item</li></ul>
    </ul>|end list
    """

    def create_contents(self, parent):
        control = PyClickableHtmlWindow(parent, -1, style=wx.NO_FULL_REPAINT_ON_RESIZE, size=(400, 300))
        control.SetPage(self.get_help_text())
        return control

    def get_help_text(self):
        lines = ["<table><tr><th>%s</th><th>%s</th>" % (self.code_header, self.desc_header)]
        for line in self.help_text.splitlines():
            if "|" in line:
                code, desc = line.split("|", 1)
                code = cgi.escape(code).replace("[RET]", "<br>")
                lines.append("<tr><td><tt>%s</tt></td><td>%s</td></tr>\n" % (code, desc))
            else:
                lines.append("<tr><td colspan=2>%s</td></tr>" % line)
        lines.append("</table>")
        return "\n".join(lines)


class RSTHelpPane(HtmlHelpPane):
    #### TaskPane interface ###################################################

    id = 'maproom.rst_markup_help_pane'
    name = 'RST Help'
    help_text = """#*****[RET]Title[RET]*****|<h1>Title</h1>
    Section[RET]=======|<h2>Section</h2>
    Subsection[RET]----------|<h3>Subsection</h3>Separate paragraphs or new lists by blank lines.
    *italic*|<i>italic</i>
    **bold**|<b>bold</b>
    * list item[RET]* list item|<ul><li>list item</li><li>list item</li></ul>
    """


class MarkdownHelpPane(HtmlHelpPane):
    #### TaskPane interface ###################################################

    id = 'maproom.markdown_help_pane'
    name = 'Markdown Help'
    help_text = """# Title|<h1>Title</h1>
    ## Section|<h2>Section</h2>
    ### Subsection|<h3>Subsection</h3>
    Separate paragraphs or new lists by blank lines.
    *italic*|<i>italic</i>
    **bold**|<b>bold</b>
    * list item[RET]* list item|<ul><li>list item</li><li>list item</li></ul>
    """
