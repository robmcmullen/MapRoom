import numpy as np

from command import Command, UndoInfo

class InsertPointCommand(Command):
    short_name = "pt"
    serialize_order = [
        ('layer', 'layer'),
        ('world_point', 'point'),
        ]
    
    def __init__(self, layer, world_point):
        Command.__init__(self, layer)
        self.world_point = world_point
    
    def __str__(self):
        return "Add Point #%d" % self.undo_info.index
    
    def perform(self, editor):
        self.undo_info = undo = self.layer.insert_point(self.world_point)
        self.layer.select_point(self.undo_info.index)
        lf = undo.flags.add_layer_flags(self.layer)
        lf.hidden_layer_check = True
        return undo

    def undo(self, editor):
        undo_info = self.layer.delete_point(self.undo_info.index)
        return undo_info

class MovePointsCommand(Command):
    short_name = "move_pt"
    serialize_order =  [
        ('layer', 'layer'),
        ('indexes', 'list_int'),
        ('dx', 'float'),
        ('dy', 'float'),
        ]
    
    def __init__(self, layer, indexes, dx, dy):
        Command.__init__(self, layer)
        self.indexes = indexes
        self.dx = dx
        self.dy = dy
    
    def __str__(self):
        if len(self.indexes) == 1:
            return "Move Point #%d" % self.indexes[0]
        return "Move %d Points" % len(self.indexes)
    
    def coalesce(self, next_command):
        if next_command.__class__ == self.__class__:
            if next_command.layer == self.layer and np.array_equal(next_command.indexes, self.indexes):
                self.dx += next_command.dx
                self.dy += next_command.dy
                return True
    
    def is_recordable(self):
        return len(self.indexes) > 0
    
    def perform(self, editor):
        self.undo_info = undo = UndoInfo()
        old_x = np.copy(self.layer.points.x[self.indexes])
        old_y = np.copy(self.layer.points.y[self.indexes])
        undo.data = (old_x, old_y)
        undo.flags.refresh_needed = True
        lf = undo.flags.add_layer_flags(self.layer)
        lf.layer_items_moved = True
        lf.layer_contents_added = True
        self.layer.points.x[self.indexes] += self.dx
        self.layer.points.y[self.indexes] += self.dy
        print "dx=%f, dy=%f" % (self.dx, self.dy)
        print self.indexes
        print undo.data
        return undo

    def undo(self, editor):
        (old_x, old_y) = self.undo_info.data
        self.layer.points.x[self.indexes] = old_x
        self.layer.points.y[self.indexes] = old_y
        return self.undo_info

class ChangeDepthCommand(Command):
    short_name = "depth"
    serialize_order =  [
        ('layer', 'layer'),
        ('indexes', 'list_int'),
        ('depth', 'float'),
        ]
    
    def __init__(self, layer, indexes, depth):
        Command.__init__(self, layer)
        self.indexes = indexes
        self.depth = depth
    
    def __str__(self):
        return "Set Depth to %s" % str(self.depth)
    
    def coalesce(self, next_command):
        if next_command.__class__ == self.__class__:
            if next_command.layer == self.layer and np.array_equal(next_command.indexes, self.indexes):
                self.depth = next_command.depth
                return True
    
    def is_recordable(self):
        return len(self.indexes) > 0
    
    def perform(self, editor):
        self.undo_info = undo = UndoInfo()
        old_depths = np.copy(self.layer.points.z[self.indexes])
        undo.data = old_depths
        undo.flags.refresh_needed = True
        lf = undo.flags.add_layer_flags(self.layer)
        lf.layer_items_moved = True
        self.layer.points.z[self.indexes] = self.depth
        return undo

    def undo(self, editor):
        (old_depths) = self.undo_info.data
        self.layer.points.z[self.indexes] = old_depths
        return self.undo_info

class InsertLineCommand(Command):
    short_name = "line_to"
    serialize_order =  [
            ('layer', 'layer'),
            ('index', 'int'),
            ('world_point', 'point'),
            ]
    
    def __init__(self, layer, index, world_point):
        Command.__init__(self, layer)
        self.index = index
        self.world_point = world_point
        self.undo_point = None
        self.undo_line = None
    
    def __str__(self):
        return "Line From Point %d" % self.index
    
    def perform(self, editor):
        self.undo_point = self.layer.insert_point(self.world_point)
        self.undo_line = self.layer.insert_line_segment(self.undo_point.index, self.index)
        self.layer.select_point(self.undo_point.index)
        lf = self.undo_point.flags.add_layer_flags(self.layer)
        lf.hidden_layer_check = True
        # FIXME: merge undo status
        return self.undo_point

    def undo(self, editor):
        # FIXME: merge undo status
        undo_info = self.layer.delete_line_segment(self.undo_line.index)
        undo_info = self.layer.delete_point(self.undo_point.index)
        return undo_info

class ConnectPointsCommand(Command):
    short_name = "line"
    serialize_order =  [
            ('layer', 'layer'),
            ('index1', 'int'),
            ('index2', 'int'),
            ]
    
    def __init__(self, layer, index1, index2):
        Command.__init__(self, layer)
        self.index1 = index1
        self.index2 = index2
        self.undo_line = None
    
    def __str__(self):
        return "Line Connecting Points %d & %d" % (self.index1, self.index2)
    
    def perform(self, editor):
        self.undo_line = self.layer.insert_line_segment(self.index1, self.index2)
        self.layer.select_point(self.index2)
        lf = self.undo_line.flags.add_layer_flags(self.layer)
        lf.hidden_layer_check = True
        return self.undo_line

    def undo(self, editor):
        undo_info = self.layer.delete_line_segment(self.undo_line.index)
        return undo_info

class SplitLineCommand(Command):
    short_name = "split"
    serialize_order =  [
            ('layer', 'layer'),
            ('index', 'int'),
            ('world_point', 'point'),
            ]
    
    def __init__(self, layer, index, world_point):
        Command.__init__(self, layer)
        self.index = index
        self.world_point = world_point
        self.undo_point = None
        self.undo_delete = None
        self.undo_line1 = None
        self.undo_line2 = None
    
    def __str__(self):
        return "Split Line #%d" % self.index
    
    def perform(self, editor):
        self.undo_point = self.layer.insert_point(self.world_point)
        
        layer = self.layer
        layer.select_point(self.undo_point.index)
        point_index_1 = layer.line_segment_indexes.point1[self.index]
        point_index_2 = layer.line_segment_indexes.point2[self.index]
        color = layer.line_segment_indexes.color[self.index]
        state = layer.line_segment_indexes.state[self.index]
        depth = (layer.points.z[point_index_1] + layer.points.z[point_index_2])/2
        layer.points.z[self.undo_point.index] = depth
        self.undo_delete = layer.delete_line_segment(self.index)
        self.undo_line1 = layer.insert_line_segment_at_index(len(layer.line_segment_indexes), point_index_1, self.undo_point.index, color, state)
        self.undo_line2 = layer.insert_line_segment_at_index(len(layer.line_segment_indexes), self.undo_point.index, point_index_2, color, state)

        lf = self.undo_point.flags.add_layer_flags(layer)
        lf.hidden_layer_check = True
        return self.undo_point

    def undo(self, editor):
        # FIXME: merge undo status
        undo_info = self.layer.delete_line_segment(self.undo_line2.index)
        undo_info = self.layer.delete_line_segment(self.undo_line1.index)
        self.layer.line_segment_indexes = np.insert(self.layer.line_segment_indexes, self.index, self.undo_delete.data).view(np.recarray)
        undo_info = self.layer.delete_point(self.undo_point.index)
        return undo_info

class DeleteLinesCommand(Command):
    short_name = "del"
    serialize_order =  [
            ('layer', 'layer'),
            ('point_indexes', 'list_int'),
            ('line_indexes', 'list_int'),
            ]
    
    def __init__(self, layer, point_indexes, line_indexes=None):
        Command.__init__(self, layer)
        self.point_indexes = point_indexes
        self.line_indexes = line_indexes
        self.undo_point = None
        self.undo_line = None
    
    def __str__(self):
        old_points, old_line_segments, old_line_indexes = self.undo_info.data
        if len(old_line_indexes) == 1:
            return "Delete Line #%d" % self.line_indexes[0]
        return "Delete %d Lines" % len(old_line_indexes)
    
    def perform(self, editor):
        self.undo_info = undo = UndoInfo()
        old_line_indexes = self.layer.get_lines_connected_to_points(self.point_indexes)
        if self.line_indexes is not None:
            # handle degenerate list as well as zero-length numpy array using length test
            if len(list(self.line_indexes)) > 0:
                old_line_indexes = np.unique(np.append(old_line_indexes, self.line_indexes))
        old_line_segments = np.copy(self.layer.line_segment_indexes[old_line_indexes])
        old_points = np.copy(self.layer.points[self.point_indexes])
        undo.data = (old_points, old_line_segments, old_line_indexes)
        print "DeleteLinesCommand: (point indexes, points, line segments, line indexes) %s %s" % (self.point_indexes, str(undo.data))
        undo.flags.refresh_needed = True
        lf = undo.flags.add_layer_flags(self.layer)
        lf.layer_items_moved = True
        lf.layer_contents_deleted = True
        self.layer.remove_points_and_lines(self.point_indexes, old_line_indexes)
        return undo

    def undo(self, editor):
        """
        Using the batch numpy.insert, it expects the point indexes to be
        relative to the current state of the array, not the original indexes.

        >>> a=np.arange(10)
        >>> a
        array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        >>> indexes=[2,5,7,9]
        >>> b=np.delete(a,indexes,0)
        >>> b
        array([0, 1, 3, 4, 6, 8])
        >>> np.insert(b, indexes, indexes)
        IndexError: index 12 is out of bounds for axis 1 with size 10
        >>> fixed = indexes - np.arange(4)
        >>> np.insert(b, fixed, indexes)
        array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        """
        old_points, old_line_segments, old_line_indexes = self.undo_info.data
        offset = np.arange(len(self.point_indexes))
        indexes = self.point_indexes - offset
        self.layer.points = np.insert(self.layer.points, indexes, old_points).view(np.recarray)

        # adjust existing indexes to allow for inserted points
        offsets1 = np.zeros(np.alen(self.layer.line_segment_indexes))
        offsets2 = np.zeros(np.alen(self.layer.line_segment_indexes))
        insertion_space = 0
        for index in indexes:
            offsets1 += np.where(self.layer.line_segment_indexes.point1 >= index, 1, 0)
            offsets2 += np.where(self.layer.line_segment_indexes.point2 >= index, 1, 0)
        self.layer.line_segment_indexes.point1 += offsets1
        self.layer.line_segment_indexes.point2 += offsets2

        offset = np.arange(len(old_line_indexes))
        indexes = old_line_indexes - offset
        self.layer.line_segment_indexes = np.insert(self.layer.line_segment_indexes, indexes, old_line_segments).view(np.recarray)
        undo = UndoInfo()
        undo.flags.refresh_needed = True
        lf = undo.flags.add_layer_flags(self.layer)
        lf.layer_items_moved = True
        lf.layer_contents_deleted = True
        return undo

class MergePointsCommand(DeleteLinesCommand):
    short_name = "merge_pt"
    serialize_order =  [
            ('layer', 'layer'),
            ('point_indexes', 'list_int'),
            ]
    
    def __init__(self, layer, point_indexes):
        DeleteLinesCommand.__init__(self, layer, point_indexes, None)
    
    def __str__(self):
        return "Merge Points"
    
class CropRectCommand(Command):
    short_name = "crop"
    serialize_order =  [
            ('layer', 'layer'),
            ('world_rect', 'rect'),
            ]
    
    def __init__(self, layer, world_rect):
        Command.__init__(self, layer)
        self.world_rect = world_rect
    
    def __str__(self):
        return "Crop"
    
    def perform(self, editor):
        self.undo_info = self.layer.crop_rectangle(self.world_rect)
        return self.undo_info

    def undo(self, editor):
        old_state = self.undo_info.data
        undo_info = self.layer.set_state(old_state)
        return undo_info
    
class LayerColorCommand(Command):
    short_name = "color"
    serialize_order =  [
            ('layer', 'layer'),
            ('color', 'int'),
            ]
    
    def __init__(self, layer, color):
        Command.__init__(self, layer)
        self.color = color
    
    def __str__(self):
        return "Layer Color"
    
    def perform(self, editor):
        self.undo_info = undo = UndoInfo()
        undo.data = (self.layer.color, self.color)
        lf = undo.flags.add_layer_flags(self.layer)
        lf.layer_display_properties_changed = True
        self.layer.set_color(self.color)
        return undo

    def undo(self, editor):
        old_color, color = self.undo_info.data
        self.layer.set_color(old_color)
        return self.undo_info
