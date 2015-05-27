import os
import sys
import wx
try:
    import wx.lib.agw.customtreectrl as treectrl
except ImportError:
    import wx.lib.customtreectrl as treectrl

from layers import Layer


import logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

class LayerTreeControl(treectrl.CustomTreeCtrl):

    dragged_item = None

    def __init__(self, parent_window, project, size=(-1,-1)):
        treectrl.CustomTreeCtrl.__init__(
            self, parent_window, wx.ID_ANY, size=size,
            style=treectrl.TR_DEFAULT_STYLE,
            agwStyle=treectrl.TR_HIDE_ROOT|treectrl.TR_NO_LINES|treectrl.TR_HAS_BUTTONS,
        )
        self.project = project
        
        self.Bind(treectrl.EVT_TREE_ITEM_CHECKED, self.handle_item_checked)
        self.Bind(treectrl.EVT_TREE_ITEM_COLLAPSED, self.handle_item_collapsed)
        self.Bind(treectrl.EVT_TREE_ITEM_EXPANDED, self.handle_item_expanded)
        self.Bind(treectrl.EVT_TREE_BEGIN_DRAG, self.handle_begin_drag)
        self.Bind(treectrl.EVT_TREE_END_DRAG, self.handle_end_drag)
        self.Bind(treectrl.EVT_TREE_SEL_CHANGED, self.handle_selection_changed)

        """
        self.state_image_list = wx.ImageList( self.IMAGE_SIZE, self.IMAGE_SIZE )
        #self.state_image_list.Add( wx.Bitmap( "maproom/ui/images/maproom.png", wx.BITMAP_TYPE_PNG ) )
        #self.SetImageList( self.state_image_list )
        """

        self.Bind(wx.EVT_LEFT_DOWN, self.mouse_pressed)
        self.Bind(wx.EVT_RIGHT_DOWN, self.mouse_pressed)
        # self.Bind( wx.EVT_RIGHT_UP, self.mouse_right_released )
        if sys.platform.startswith("win"):
            self.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_wheel_scroll)
    
    def set_project(self, project):
        self.project = project
        self.rebuild()

    def get_selected_layer(self):
        item = self.GetSelection()
        if (item is None):
            return None
        (category, layer) = self.GetItemPyData(item).Data

        return layer

    def is_selected_layer(self, layer):
        item = self.GetSelection()
        if (item is None):
            return False
        (category, selected) = self.GetItemPyData(item).Data
        return layer == selected

    def select_layer(self, layer):
        if self.project is None:
            return
        self.project.clear_all_selections(False)

        if (layer is None):
            self.UnselectAll()
        else:
            self.select_layer_recursive(layer, self.GetRootItem())

    def select_layer_recursive(self, layer, item):
        (category, item_layer) = self.GetItemPyData(item).Data

        if (item_layer == layer):
            self.SelectItem(item, True)
            # also make sure the layer's name is up-to-date
            self.SetItemText(item, layer.name)
            layer.set_visibility_when_selected(self.project.layer_visibility[layer])

            return True

        if (not self.ItemHasChildren(item)):
            return False

        n = self.GetChildrenCount(item, False)
        # apparently GetFirstChild() returns a tuple of the
        # child and an integer (I think the integer is the "cookie" for calling GetNextChild())
        child = self.GetFirstChild(item)[0]

        while (n > 0):
            if (self.select_layer_recursive(layer, child)):
                return True

            child = self.GetNextSibling(child)
            n -= 1

        return False

    def rebuild(self):
        # rebuild the tree from the layer manager's data
        if self.project is None:
            # Wait till there's an active project
            return
        selected = self.get_selected_layer()
        lm = self.project.layer_manager
        self.DeleteAllItems()
        # self.Freeze()
        log.debug("LAYER_TREE: rebuiding layers = " + str(lm.layers))
        self.add_layers_recursive(lm.layers, None)
        # self.Thaw()
        self.select_layer(selected)
        self.project.update_layer_selection_ui(selected)

    def add_layers_recursive(self, layer_tree, parent):
        if (len(layer_tree) == 0):
            return

        # we assume the layer at the start of each list is a folder
        folder_node = self.add_layer(layer_tree[0], parent)
        # import code; code.interact( local = locals() )

        for item in layer_tree[1:]:
            if (isinstance(item, Layer)):
                node = self.add_layer(item, folder_node)
            else:
                self.add_layers_recursive(item, folder_node)

    def add_layer(self, layer, parent):
        log.debug("LAYER_TREE: adding layer = " + str(layer.name))
        if (parent is None):
            data = wx.TreeItemData()
            data.SetData(("root", layer))
            return self.AddRoot(layer.name, data=data)

        data = wx.TreeItemData()
        if layer.is_folder():
            data.SetData(("folder", layer))
        else:
            data.SetData(("layer", layer))

        vis = self.project.layer_visibility[layer]
        item = self.AppendItem(parent, layer.name, ct_type=treectrl.TREE_ITEMTYPE_CHECK, data=data)
        self.CheckItem2(item, vis["layer"])

        if (layer.is_expanded):
            self.Expand(item)

        return item

    def remove_layer(self, layer, parent=None):
        item = self.layer_to_item.get(layer)
        if item is None:
            return

        self.Freeze()
        self.Delete(item)

        if self.GetChildrenCount(self.root) == 0:
            self.none_item = self.AppendItem(self.root, "None")

        self.Thaw()

        self.layer_to_item.pop(layer, None)

    def handle_item_checked(self, event):
        (category, layer) = self.GetItemPyData(event.GetItem()).Data
        item = event.GetItem()
        checked = self.IsItemChecked(item)
        vis = self.project.layer_visibility[layer]
        vis[category] = checked
        self.project.refresh()
        event.Skip()

    def handle_item_collapsed(self, event):
        pd = self.GetItemPyData(event.GetItem())
        if (pd is None):
            return

        (category, layer) = pd.Data
        layer.is_expanded = False

    def handle_item_expanded(self, event):
        pd = self.GetItemPyData(event.GetItem())
        if (pd is None):
            return

        (category, layer) = pd.Data
        layer.is_expanded = True

    def handle_begin_drag(self, event):
        (category, layer) = self.GetItemPyData(event.GetItem()).Data
        item = event.GetItem()
        checked = self.IsItemChecked(item)
        if (category == "folder" or category == "layer"):
            event.Allow()
            self.dragged_item = item

    def handle_end_drag(self, event):
        item = event.GetItem()
        local_dragged_item = self.dragged_item
        self.dragged_item = None

        # if we dropped somewhere that isn't on top of an item, ignore the event
        if item is None or not item.IsOk():
            return

        (target_category, target_layer) = self.GetItemPyData(item).Data
        if (target_category != "root" and target_category != "folder" and target_category != "layer"):
            self.project.window.error("You can only drag a layer onto another layer, a folder, or the tree root.", "Invalid Layer Drag")
            return

        (source_category, source_layer) = self.GetItemPyData(local_dragged_item).Data
        lm = self.project.layer_manager
        mi_source = lm.get_multi_index_of_layer(source_layer)
        # here we "re-get" the source layer so that if it's a folder layer what we'll get is the
        # folder's list, not just the folder pseudo-layer
        source_layer = lm.get_layer_by_multi_index(mi_source)

        mi_target = lm.get_multi_index_of_layer(target_layer)

        if (mi_target == mi_source):
            return

        if (len(mi_target) > len(mi_source) and mi_target[0: len(mi_source)] == mi_source):
            self.project.window.error("You cannot move folder into one of its sub-folders.", "Invalid Layer Move")
            return

        lm.remove_layer_at_multi_index(mi_source)

        # re-get the multi_index for the target, because it may have changed when the layer was removed
        mi_target = lm.get_multi_index_of_layer(target_layer)
        # if we are inserting onto a folder, insert as the second item in the folder
        # (the first item in the folder is the folder pseudo-layer)
        if (target_category == "root"):
            mi_target = [1]
        elif (target_category == "folder"):
            mi_target.append(1)
        lm.insert_layer(mi_target, source_layer)
        self.select_layer(source_layer)
        self.rebuild()

    def handle_selection_changed(self, event):
        self.project.clear_all_selections(False)
        layer = self.get_selected_layer()
        self.project.update_layer_selection_ui(layer)
        layer.set_visibility_when_selected(self.project.layer_visibility[layer])
        self.project.refresh()

    def raise_selected_layer(self):
        self.move_selected_layer(-1)

    def raise_to_top(self):
        self.move_selected_layer(-1, True)

    def lower_to_bottom(self):
        self.move_selected_layer(1, True)

    def lower_selected_layer(self):
        self.move_selected_layer(1)

    def move_selected_layer(self, delta, to_extreme=False):
        item = self.GetSelection()
        (category, layer) = self.GetItemPyData(item).Data
        lm = self.project.layer_manager
        mi_source = lm.get_multi_index_of_layer(layer)
        mi_target = mi_source[: len(mi_source) - 1]
        if to_extreme:
            if delta < 0:
                mi_target.append(1)  # zeroth index is folder
            else:
                mi2 = mi_source[: len(mi_source) - 1]
                parent_list = lm.get_layer_by_multi_index(mi2)
                total = len(parent_list)
                mi_target.append(total)
        else:
            mi_target.append(mi_source[len(mi_source) - 1] + delta)

        # here we "re-get" the source layer so that if it's a folder layer what we'll get is the
        # folder's list, not just the folder pseudo-layer
        source_layer = lm.get_layer_by_multi_index(mi_source)
        lm.remove_layer_at_multi_index(mi_source)
        lm.insert_layer(mi_target, source_layer)
        self.project.clear_all_selections(False)
        self.select_layer(layer)
        self.rebuild()

    def mouse_pressed(self, event):
        # If a selected item is clicked, unselect it so that it will be
        # selected again. This allows the user to click on an
        # already-selected layer to display its properties, for instance.
        event.Skip()
        selected_item = self.GetSelection()
        if selected_item is None:
            return

        (clicked_item, flags) = self.HitTest(event.GetPosition())

        if clicked_item != selected_item or \
           flags & wx.TREE_HITTEST_ONITEMLABEL == 0:
            return

        self.ToggleItemSelection(selected_item)

    def on_mouse_wheel_scroll(self, event):
        screen_point = event.GetPosition()
        size = self.GetSize()
        if screen_point.x < 0 or screen_point.y < 0 or screen_point.x > size.x or screen_point.y > size.y:
#            print "Mouse not over Tree: trying map!"
            if self.project is not None:
                self.project.control.on_mouse_wheel_scroll(event)
            return
        
        event.Skip()