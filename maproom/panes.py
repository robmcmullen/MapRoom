"""Sample panes for Skeleton

"""
# Enthought library imports.
from pyface.tasks.api import DockPane, TraitsDockPane
from traits.api import on_trait_change

from Layer_tree_control import Layer_tree_control
from ui.InfoPanels import LayerInfoPanel, SelectionInfoPanel
from ui.TrianglePanel import TrianglePanel

class LayerSelectionPane(DockPane):
    #### TaskPane interface ###################################################

    id = 'maproom.layer_selection_pane'
    name = 'Layers'
    
    def create_contents(self, parent):
        control = Layer_tree_control(parent, self.task.active_editor, size=(200,-1))
        return control
    
    #### trait change handlers
    
    def _task_changed(self):
        print "TASK CHANGED IN LAYERSELECTIONPANE!!!! %s" % self.task
        if self.control:
            self.control.set_project(self.task.active_editor)

# FIXME: Even this simple trait change handler that just prints something will
# occasionally result in a segfault.  Have to use the trait change handler in
# the task itself, rather than referencing the task here.
#
#    @on_trait_change('task.active_editor')
#    def _active_editor_changed(self):
#        print "ACTIVE EDITOR CHANGED IN LayerSelectionPane!!!! %s" % self.task.active_editor


class LayerInfoPane(DockPane):
    #### TaskPane interface ###################################################

    id = 'maproom.layer_info_pane'
    name = 'Current Layer'
    
    def create_contents(self, parent):
        control = LayerInfoPanel(parent, self.task.active_editor)
        return control


class SelectionInfoPane(DockPane):
    #### TaskPane interface ###################################################

    id = 'maproom.selection_info_pane'
    name = 'Current Selection'
    
    def create_contents(self, parent):
        control = SelectionInfoPanel(parent, self.task.active_editor)
        return control


class TriangulatePane(DockPane):
    #### TaskPane interface ###################################################

    id = 'maproom.triangulate_pane'
    name = 'Triangulate'
    
    def create_contents(self, parent):
        control = TrianglePanel(parent, self.task)
        return control
    
    #### trait change handlers
    
    def _task_changed(self):
        print "TASK CHANGED IN TRIANGULATEPANE!!!! %s" % self.task
        if self.control:
            self.control.set_task(self.task)
