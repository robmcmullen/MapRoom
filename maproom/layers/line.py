import os
import os.path
import time
import sys
import numpy as np

# Enthought library imports.
from traits.api import Int, Unicode, Any, Str, Float, Enum, Property

from ..library import rect
from ..library.Boundary import Boundaries, PointsError
from ..renderer import color_to_int, data_types
from ..layer_undo import *
from ..command import UndoInfo
from ..mouse_commands import DeleteLinesCommand

from point import PointLayer
from constants import *

import logging
log = logging.getLogger(__name__)
progress_log = logging.getLogger("progress")


class LineLayer(PointLayer):
    """Layer for points/lines/polygons.
    
    """
    name = Unicode("Ugrid Layer")
    
    type = Str("line")
    
    line_segment_indexes = Any

    pickable = True # is this a layer that support picking?

    def __str__(self):
        try:
            lines = len(self.line_segment_indexes)
        except:
            lines = 0
        return PointLayer.__str__(self) + ", %d lines" % lines
    
    def get_visibility_items(self):
        """Return allowable keys for visibility dict lookups for this layer
        """
        return ["points", "lines", "labels"]
    
    def visibility_item_exists(self, label):
        """Return keys for visibility dict lookups that currently exist in this layer
        """
        if label in ["points", "labels"]:
            return self.points is not None
        if label == "lines":
            return self.line_segment_indexes is not None
        raise RuntimeError("Unknown label %s for %s" % (label, self.name))

    def set_data(self, f_points, f_depths, f_line_segment_indexes):
        n = np.alen(f_points)
        self.determine_layer_color()
        self.points = self.make_points(n)
        if (n > 0):
            self.points.view(data_types.POINT_XY_VIEW_DTYPE).xy[
                0: n
            ] = f_points
            self.points.z[
                0: n
            ] = f_depths
            self.points.color = self.color
            self.points.state = 0

            n = np.alen(f_line_segment_indexes)
            self.line_segment_indexes = self.make_line_segment_indexes(n)
            self.line_segment_indexes.view(data_types.LINE_SEGMENT_POINTS_VIEW_DTYPE).points[
                0: n
            ] = f_line_segment_indexes
            self.line_segment_indexes.color = self.color
            self.line_segment_indexes.state = 0
        
        self.update_bounds()

    def can_save_as(self):
        return True
    
    def serialize_json(self, index):
        json = PointLayer.serialize_json(self, index)
        update = {
            'lines': self.line_segment_indexes.tolist(),
        }
        json.update(update)
        return json
    
    def unserialize_json_version1(self, json_data):
        PointLayer.unserialize_json_version1(self, json_data)
        self.line_segment_indexes = np.array([tuple(i) for i in json_data['lines']], data_types.LINE_SEGMENT_DTYPE).view(np.recarray)
    
    def check_for_problems(self, window):
        # determine the boundaries in the parent layer
        boundaries = Boundaries(self, allow_branches=False, allow_self_crossing=False)
        boundaries.check_errors(True)
    
    def select_outer_boundary(self):
        # determine the boundaries in the parent layer
        boundaries = Boundaries(self, allow_branches=True, allow_self_crossing=True)
        if len(boundaries) > 0:
            self.select_points(boundaries[0].point_indexes)
        else:
            return None
        return boundaries[0]

    def make_line_segment_indexes(self, count):
        return np.repeat(
            np.array([(0, 0, 0, 0)], dtype=data_types.LINE_SEGMENT_DTYPE),
            count,
        ).view(np.recarray)

    def clear_all_selections(self, mark_type=STATE_SELECTED):
        self.clear_all_point_selections(mark_type)
        self.clear_all_line_segment_selections(mark_type)
        self.increment_change_count()

    def clear_all_line_segment_selections(self, mark_type=STATE_SELECTED):
        if (self.line_segment_indexes != None):
            self.line_segment_indexes.state = self.line_segment_indexes.state & (0xFFFFFFFF ^ mark_type)
            self.increment_change_count()

    def select_line_segment(self, line_segment_index, mark_type=STATE_SELECTED):
        self.line_segment_indexes.state[line_segment_index] = self.line_segment_indexes.state[line_segment_index] | mark_type
        self.increment_change_count()

    def deselect_line_segment(self, line_segment_index, mark_type=STATE_SELECTED):
        self.line_segment_indexes.state[line_segment_index] = self.line_segment_indexes.state[line_segment_index] & (0xFFFFFFFF ^ mark_type)
        self.increment_change_count()

    def is_line_segment_selected(self, line_segment_index, mark_type=STATE_SELECTED):
        return self.line_segment_indexes != None and (self.line_segment_indexes.state[line_segment_index] & mark_type) != 0

    def select_line_segments_in_rect(self, is_toggle_mode, is_add_mode, w_r, mark_type=STATE_SELECTED):
        if (not is_toggle_mode and not is_add_mode):
            self.clear_all_line_segment_selections()
        point_indexes = np.where(np.logical_and(
            np.logical_and(self.points.x >= w_r[0][0], self.points.x <= w_r[1][0]),
            np.logical_and(self.points.y >= w_r[0][1], self.points.y <= w_r[1][1])))[0]
        indexes = np.where(np.logical_or(
            np.in1d(self.line_segment_indexes.point1, point_indexes),
            np.in1d(self.line_segment_indexes.point2, point_indexes)))
        if (is_add_mode):
            self.line_segment_indexes.state[indexes] |= mark_type
        if (is_toggle_mode):
            self.line_segment_indexes.state[indexes] ^= mark_type
        self.increment_change_count()

    def get_selected_and_dependent_point_indexes(self, mark_type=STATE_SELECTED):
        indexes = np.arange(0)
        if (self.points != None):
            indexes = np.append(indexes, self.get_selected_point_indexes(mark_type))
        if (self.line_segment_indexes != None):
            l_s_i_s = self.get_selected_line_segment_indexes(mark_type)
            indexes = np.append(indexes, self.line_segment_indexes[l_s_i_s].point1)
            indexes = np.append(indexes, self.line_segment_indexes[l_s_i_s].point2)
        #
        return np.unique(indexes)

    def get_num_points_selected(self, mark_type=STATE_SELECTED):
        return len(self.get_selected_and_dependent_point_indexes(mark_type))

    def get_selected_line_segment_indexes(self, mark_type=STATE_SELECTED):
        if (self.line_segment_indexes == None):
            return []
        #
        return np.where((self.line_segment_indexes.state & mark_type) != 0)[0]

    def get_all_line_point_indexes(self):
        indexes = np.arange(0)
        if (self.line_segment_indexes != None):
            indexes = np.append(indexes, self.line_segment_indexes.point1)
            indexes = np.append(indexes, self.line_segment_indexes.point2)
        #
        return np.unique(indexes)

    def find_points_on_shortest_path_from_point_to_selected_point(self, point_index):
        return self.follow_point_paths_to_selected_point([[point_index]])

    def follow_point_paths_to_selected_point(self, list_of_paths):
        while True:
            if (list_of_paths == []):
                return []

            new_paths = []
            for path in list_of_paths:
                # consider the last point in the path
                # find all other points connected to this point that are not already in path
                # if one such point is selected, we found the path
                # otherwise, add the point to the path to be followed further
                p = path[len(path) - 1]
                connections = self.find_points_connected_to_point(p)
                for q in connections:
                    if (not q in path):
                        extended = []
                        extended.extend(path)
                        extended.append(q)
                        if (self.is_point_selected(q)):
                            return extended
                        else:
                            new_paths.append(extended)

            list_of_paths = new_paths

    def find_points_connected_to_point(self, point_index):
        if (self.line_segment_indexes == None):
            return []

        result = []
        indexes = self.line_segment_indexes[self.line_segment_indexes.point1 == point_index]
        result.extend(indexes.point2)
        indexes = self.line_segment_indexes[self.line_segment_indexes.point2 == point_index]
        result.extend(indexes.point1)

        return list(set(result))

    def are_points_connected(self, point_index_1, point_index_2):
        return point_index_2 in self.find_points_connected_to_point(point_index_1)

    def find_lines_on_shortest_path_from_line_to_selected_line(self, line_segment_index):
        return self.follow_line_paths_to_selected_line([[line_segment_index]])

    def follow_line_paths_to_selected_line(self, list_of_paths):
        while True:
            if (list_of_paths == []):
                return []

            new_paths = []
            for path in list_of_paths:
                # consider the last line segment in the path
                # find all other line segments connected to this line segment that are not already in path
                # if one such line segment is selected, we found the path
                # otherwise, add the line segment to the path to be followed further
                i = path[len(path) - 1]
                connections = self.find_lines_connected_to_line(i)
                for j in connections:
                    if (not j in path):
                        extended = []
                        extended.extend(path)
                        extended.append(j)
                        if (self.is_line_segment_selected(j)):
                            return extended
                        else:
                            new_paths.append(extended)

            list_of_paths = new_paths

    def find_lines_connected_to_line(self, line_segment_index):
        if (self.line_segment_indexes == None):
            return []

        p1 = self.line_segment_indexes.point1[line_segment_index]
        p2 = self.line_segment_indexes.point2[line_segment_index]
        result = np.arange(0)
        result = np.append(result, np.where(self.line_segment_indexes.point1 == p1))
        result = np.append(result, np.where(self.line_segment_indexes.point1 == p2))
        result = np.append(result, np.where(self.line_segment_indexes.point2 == p1))
        result = np.append(result, np.where(self.line_segment_indexes.point2 == p2))

        s = set(result)
        s.remove(line_segment_index)

        return list(s)

    def delete_all_selected_objects(self):
        point_indexes = self.get_selected_point_indexes()
        l_s_i_s = None
        if (self.get_selected_line_segment_indexes != None):
            l_s_i_s = self.get_selected_line_segment_indexes()
        if ((point_indexes != None and len(point_indexes)) > 0 or (l_s_i_s != None and len(l_s_i_s) > 0)):
            cmd = DeleteLinesCommand(self, point_indexes, l_s_i_s)
            return cmd

    def get_lines_connected_to_points(self, point_indexes):
        if point_indexes is None:
            return []
        attached = np.where(np.in1d(self.line_segment_indexes.point1, point_indexes))
        attached = np.append(attached, np.where(np.in1d(self.line_segment_indexes.point2, point_indexes)))
        attached = np.unique(attached)
        return attached

    def remove_points_and_lines(self, point_indexes, line_segment_indexes_to_be_deleted):
        # adjust the point indexes of the remaining line segments
        offsets = np.zeros(np.alen(self.line_segment_indexes))
        for index in point_indexes:
            offsets += np.where(self.line_segment_indexes.point1 > index, 1, 0)
        self.line_segment_indexes.point1 -= offsets
        offsets[: np.alen(offsets)] = 0
        for index in point_indexes:
            offsets += np.where(self.line_segment_indexes.point2 > index, 1, 0)
        self.line_segment_indexes.point2 -= offsets

        # delete them from the layer
        self.points = np.delete(self.points, point_indexes, 0)
        if (line_segment_indexes_to_be_deleted != None):
            # then delete the line segments
            self.line_segment_indexes = np.delete(self.line_segment_indexes, line_segment_indexes_to_be_deleted, 0)

    def update_after_insert_point_at_index(self, point_index):
        # update point indexes in the line segements to account for the inserted point
        if (self.line_segment_indexes != None):
            offsets = np.zeros(np.alen(self.line_segment_indexes))
            offsets += np.where(self.line_segment_indexes.point1 >= point_index, 1, 0)
            self.line_segment_indexes.point1 += offsets
            offsets[: np.alen(offsets)] = 0
            offsets += np.where(self.line_segment_indexes.point2 >= point_index, 1, 0)
            self.line_segment_indexes.point2 += offsets
    
    def insert_point_in_line(self, world_point, line_segment_index):
        new_point_index = self.insert_point(world_point)
        point_index_1 = self.line_segment_indexes.point1[line_segment_index]
        point_index_2 = self.line_segment_indexes.point2[line_segment_index]
        color = self.line_segment_indexes.color[line_segment_index]
        state = self.line_segment_indexes.state[line_segment_index]
        depth = (self.points.z[point_index_1] + self.points.z[point_index_2])/2
        self.points.z[new_point_index] = depth
        self.delete_line_segment(line_segment_index, True)
        self.insert_line_segment_at_index(len(self.line_segment_indexes), point_index_1, new_point_index, color, state, True)
        self.insert_line_segment_at_index(len(self.line_segment_indexes), new_point_index, point_index_2, color, state, True)

        return new_point_index

    """
    def connect_points_to_point( self, point_indexes, point_index ):
        connected_points = self.find_points_connected_to_point( point_index )
        num_connections_made = 0
        for p_i in point_indexes:
            if ( p_i != point_index and not ( p_i in connected_points ) ):
                l_s = np.array( [ ( p_i, point_index, DEFAULT_LINE_SEGMENT_COLOR, STATE_NONE ) ],
                                dtype = data_types.LINE_SEGMENT_DTYPE ).view( np.recarray )
                self.line_segment_indexes = np.append( self.line_segment_indexes, l_s ).view( np.recarray )
                num_connections_made += 1
        if ( num_connections_made > 0 ):
            self.rebuild_point_and_line_set_renderer()
    """

    def insert_line_segment(self, point_index_1, point_index_2):
        return self.insert_line_segment_at_index(len(self.line_segment_indexes), point_index_1, point_index_2, self.color, STATE_NONE)

    def insert_line_segment_at_index(self, l_s_i, point_index_1, point_index_2, color, state):
        l_s = np.array([(point_index_1, point_index_2, color, state)],
                       dtype=data_types.LINE_SEGMENT_DTYPE).view(np.recarray)
        self.line_segment_indexes = np.insert(self.line_segment_indexes, l_s_i, l_s).view(np.recarray)

        undo = UndoInfo()
        undo.index = l_s_i
        undo.data = np.copy(l_s)
        undo.flags.layer_contents_added = self

        return undo

    def update_after_delete_point(self, point_index):
        if (self.line_segment_indexes != None):
            offsets = np.zeros(np.alen(self.line_segment_indexes))
            offsets += np.where(self.line_segment_indexes.point1 > point_index, 1, 0)
            self.line_segment_indexes.point1 -= offsets
            offsets[: np.alen(offsets)] = 0
            offsets += np.where(self.line_segment_indexes.point2 > point_index, 1, 0)
            self.line_segment_indexes.point2 -= offsets

    def delete_line_segment(self, l_s_i):
        undo = UndoInfo()
        p = self.line_segment_indexes[l_s_i]
        print "LABEL: deleting line: %s" % str(p)
        undo.index = l_s_i
        undo.data = np.copy(p)
        undo.flags.refresh_needed = True
        undo.flags.layer_contents_deleted = self

        self.line_segment_indexes = np.delete(self.line_segment_indexes, l_s_i, 0)

    def merge_from_source_layers(self, layer_a, layer_b):
        # for now we only handle merging of points and lines
        self.new()
        
        self.merged_points_index = len(layer_a.points)

        n = len(layer_a.points) + len(layer_b.points)
        self.points = self.make_points(n)
        self.points[
            0: len(layer_a.points)
        ] = layer_a.points.copy()
        self.points[
            len(layer_a.points): n
        ] = layer_b.points.copy()
        # self.points.state = 0

        n = len(layer_a.line_segment_indexes) + len(layer_b.line_segment_indexes)
        self.line_segment_indexes = self.make_line_segment_indexes(n)
        self.line_segment_indexes[
            0: len(layer_a.line_segment_indexes)
        ] = layer_a.line_segment_indexes.copy()
        l_s_i_s = layer_b.line_segment_indexes.copy()
        # offset line segment point indexes to account for their new position in the merged array
        l_s_i_s.point1 += len(layer_a.points)
        l_s_i_s.point2 += len(layer_a.points)
        self.line_segment_indexes[
            len(layer_a.line_segment_indexes): n
        ] = l_s_i_s
        # self.line_segment_indexes.state = 0

    # returns a list of pairs of point indexes
    def find_duplicates(self, distance_tolerance_degrees, depth_tolerance_percentage=-1):
        if (self.points == None or len(self.points) < 2):
            return []

        points = self.points.view(
            data_types.POINT_XY_VIEW_DTYPE
        ).xy[:].copy()

        # cKDTree doesn't handle NaNs gracefully, but it does handle infinity
        # values. So replace all the NaNs with infinity.
        points = points.view(np.float64)
        points[np.isnan(points)] = np.inf

        tree = cKDTree(points)

        (_, indices_list) = tree.query(
            points,
            2,  # number of points to return per point given.
            distance_upper_bound=distance_tolerance_degrees
        )

        duplicates = set()

        for (n, indices) in enumerate(indices_list):
            # cKDTree uses the point count (the number of points in the input list) to indicate a missing neighbor, so
            # filter out those values from the results.
            indices = [
                index for index in sorted(indices)
                if index != len(self.points)
            ]

            if len(indices) < 2:
                continue

            # If this layer was merged from two layers, and if
            # all point indices in the current list are from the same source
            # layer, then skip this list of duplicates.
            if self.merged_points_index > 0:
                unique_sources = set()
                for index in indices:
                    if (index < self.merged_points_index):
                        unique_sources.add(0)
                    else:
                        unique_sources.add(1)

                if len(unique_sources) < 2:
                    continue

            # Filter out points not within the depth tolerance from one another.
            depth_0 = self.points.z[indices[0]]
            depth_1 = self.points.z[indices[1]]
            smaller_depth = min(abs(depth_0), abs(depth_1)) or 1.0

            depth_difference = abs((depth_0 - depth_1) / smaller_depth) * 100.0

            if (depth_tolerance_percentage > -1 and depth_difference > depth_tolerance_percentage):
                continue

            duplicates.add(tuple(indices))

            """
            if n % 100 == 0:
                scheduler.switch()
            """

        return list(duplicates)

    def merge_duplicates(self, indexes, points_in_lines):
        points_to_delete = set()

        for sublist in indexes:
            (point_0, point_1) = sublist
            point_0_in_line = point_0 in points_in_lines
            point_1_in_line = point_1 in points_in_lines

            # If each point in the pair is within a line, then skip it since
            # we don't know how to merge such points.
            if (point_0_in_line and point_1_in_line):
                continue

            # If only one of the points is within a line, then delete the
            # other point in the pair.
            if (point_0_in_line):
                points_to_delete.add(point_1)
            elif (point_1_in_line):
                points_to_delete.add(point_0)
            # Otherwise, arbitrarily delete one of the points
            else:
                points_to_delete.add(point_1)

        if (len(points_to_delete) > 0):
            self.delete_points_and_lines(list(points_to_delete), None, True)

        self.manager.dispatch_event('refresh_needed')
    
    def create_renderer(self, renderer):
        """Create the graphic renderer for this layer.
        
        There may be multiple views of this layer (e.g.  in different windows),
        so we can't just create the renderer as an attribute of this object.
        The storage parameter is attached to the view and independent of
        other views of this layer.
        
        """
        if self.points != None and renderer.point_and_line_set_renderer == None:
            if (self.line_segment_indexes == None):
                self.line_segment_indexes = self.make_line_segment_indexes(0)

            renderer.rebuild_point_and_line_set_renderer(self, create=True)

        renderer.set_up_labels(self)

    def render_projected(self, renderer, w_r, p_r, s_r, layer_visibility, layer_index_base, pick_mode=False):
        log.log(5, "Rendering line layer!!! visible=%s, pick=%s" % (layer_visibility["layer"], pick_mode))
        if (not layer_visibility["layer"]):
            return

        # the points and line segments
        if (renderer.point_and_line_set_renderer != None):
            renderer.point_and_line_set_renderer.render(layer_index_base + renderer.POINTS_AND_LINES_SUB_LAYER_PICKER_OFFSET,
                                                    pick_mode,
                                                    self.point_size,
                                                    self.line_width,
                                                    layer_visibility["points"],
                                                    layer_visibility["lines"],
                                                    False,
                                                    self.triangle_line_width,
                                                    self.get_selected_point_indexes(),
                                                    self.get_selected_point_indexes(STATE_FLAGGED),
                                                    self.get_selected_line_segment_indexes(),
                                                    self.get_selected_line_segment_indexes(STATE_FLAGGED))

            # the labels
            if (renderer.label_set_renderer != None and layer_visibility["labels"] and renderer.point_and_line_set_renderer.vbo_point_xys != None):
                renderer.label_set_renderer.render(-1, pick_mode, s_r,
                                               renderer.MAX_LABEL_CHARACTERS, self.points.z,
                                               renderer.point_and_line_set_renderer.vbo_point_xys.data,
                                               p_r, renderer.canvas.projected_units_per_pixel)

        # render selections after everything else
        if (renderer.point_and_line_set_renderer != None and not pick_mode):
            if layer_visibility["lines"]:
                renderer.point_and_line_set_renderer.render_selected_line_segments(self.line_width, self.get_selected_line_segment_indexes())

            if layer_visibility["points"]:
                renderer.point_and_line_set_renderer.render_selected_points(self.point_size,
                                                                        self.get_selected_point_indexes())
