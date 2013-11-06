import os
import os.path
import time
import sys
import numpy as np
from library.scipy_ckdtree import cKDTree
import wx
import library.File_loader as File_loader
import library.formats.verdat as verdat
from library.accumulator import flatten
from library.color import *
from library.Projection import *
import library.rect as rect
from library.Boundary import find_boundaries, generate_inside_hole_point, generate_outside_hole_point
from pytriangle import triangulate_simple
from Editor import *
from wx.lib.pubsub import pub
import app_globals

"""
    point: x, y, z (depth), color, state
    state = selected | flagged | deleted | edited | added | land_polygon | water_polygon | other_polygon
"""

# for the picker, we only have a total of 255 "layers" that it tracks;
# so we give each Layer 10 slots, 5 for the point-and-line renderer and
# 5 for the polygon renderer; within each renderer, these 5 are further
# divided to distinguish between points, lines, and fills; so the assumption
# here is that we won't have more than 25 actively "pickable" Layers, and
# each layer won't have more than 10 subcategories of pickable item types
# among its renderers
POINTS_AND_LINES_SUB_LAYER_PICKER_OFFSET = 0
POLYGONS_SUB_LAYER_PICKER_OFFSET = 5

STATE_NONE = 0
STATE_SELECTED = 1
STATE_FLAGGED = 2
STATE_DELETED = 4
STATE_EDITED = 8
STATE_ADDED = 16
STATE_LAND_POLYGON = 32
STATE_WATER_POLYGON = 64
STATE_OTHER_POLYGON = 128

DEFAULT_DEPTH = 1.0
DEFAULT_POINT_COLOR = color_to_int(0.5, 0.5, 0, 1.0)
DEFAULT_COLORS = [
    color_to_int(0, 0, 1.0, 1),
    color_to_int(0, 0.75, 0, 1),
    color_to_int(0.5, 0, 1.0, 1),
    color_to_int(1.0, 0.5, 0, 1),
    color_to_int(0.5, 0.5, 0, 1),
]
DEFAULT_LINE_SEGMENT_COLOR = color_to_int(0.5, 0, 0.5, 1.0)

MAX_LABEL_CHARATERS = 1000 * 5


class Layer():

    """
    A layer.
    """

    POINT_DTYPE = np.dtype([
        ("x", np.float32),
        ("y", np.float32),
        ("z", np.float32),
        ("color", np.uint32),
        ("state", np.uint32)
    ])
    POINT_XY_VIEW_DTYPE = np.dtype([
        ("xy", "2f4"),
        ("z", np.float32),
        ("color", np.uint32),
        ("state", np.uint32)
    ])
    POINT_XYZ_VIEW_DTYPE = np.dtype([
        ("xyz", "3f4"),
        ("color", np.uint32),
        ("state", np.uint32)
    ])
    LINE_SEGMENT_DTYPE = np.dtype([
        ("point1", np.uint32),  # Index of first point in line segment.
        ("point2", np.uint32),  # Index of second point in line segment.
        ("color", np.uint32),  # Color of this line segment.
        ("state", np.uint32)
    ])
    LINE_SEGMENT_POINTS_VIEW_DTYPE = np.dtype([
        ("points", "2u4"),
        ("color", np.uint32),
        ("state", np.uint32)
    ])
    TRIANGLE_DTYPE = np.dtype([
        ("point1", np.uint32),  # Index of first point in triangle.
        ("point2", np.uint32),  # Index of second point in triangle.
        ("point3", np.uint32),  # Index of third point in triangle.
        ("color", np.uint32),
        ("state", np.uint32)
    ])
    TRIANGLE_POINTS_VIEW_DTYPE = np.dtype([
        ("point_indexes", "3u4"),
        ("color", np.uint32),
        ("state", np.uint32)
    ])
    POLYGON_ADJACENCY_DTYPE = np.dtype([  # parallels the points array
        ("next", np.uint32),   # Index of next adjacent point in polygon.
        ("polygon", np.uint32)  # Index of polygon this point is in.
    ])
    POLYGON_DTYPE = np.dtype([
        ("start", np.uint32),  # Index of arbitrary point in this polygon.
        ("count", np.uint32),  # Number of points in this polygon.
        ("group", np.uint32),  # An outer polygon and all of its holes have the same opaque group id.
        ("color", np.uint32),  # Color of this polygon.
        ("state", np.uint32)   # standard maproom object states, plus polygon type
    ])

    next_default_color_index = 0

    def __init__(self):
        self.name = ""
        self.type = ""  # either "folder" (folder don't use any of the data below is_expanded) or the file suffix
        self.is_expanded = True
        self.is_visible = True

        self.file_path = ""
        self.depth_unit = "unknown"
        self.default_depth = DEFAULT_DEPTH
        self.color = 0
        self.point_size = 4.0
        self.selected_point_size = 15.0
        self.line_width = 2.0
        self.selected_line_width = 10.0
        self.triangle_line_width = 1.0
        self.bounds = rect.NONE_RECT
        self.load_error_string = ""

        # when two layers are merged into one, this is the index of the start of the points that came from the second layer
        self.merged_points_index = 0

        # this is any change that might affect the properties panel (e.g., number of points selected)
        self.change_count = 0

        self.points = None
        self.points_visible = True
        self.line_segment_indexes = None
        self.line_segments_visible = True
        self.labels_visible = True
        self.triangle_points = None
        self.triangles = None
        self.triangles_visible = True
        self.polygons = None
        self.polygons_visible = True
        self.polygon_adjacency_array = None  # parallels the points array
        self.images = None
        self.image_sizes = None
        self.image_world_rects = None
        self.images_visible = True

        self.is_dirty = False

    def __repr__(self):
        return self.name

    def new(self):
        self.name = "New Layer"
        self.determine_layer_color()
        self.points = self.make_points(0)

    def empty(self):
        """
        We shouldn't allow saving of a layer with no content, so we use this method
        to determine if we can save this layer.
        """
        no_points = (self.points is None or len(self.points) == 0)
        no_triangles = (self.triangles is None or len(self.triangles) == 0)
        no_polygons = (self.polygons is None or len(self.polygons) == 0)
        no_images = (self.images is None or len(self.images) == 0)

        return no_points and no_triangles and no_polygons and no_images

    def guess_type_from_file_contents(self, file_path):
        f = open(file_path, "r")
        line = f.readline()
        f.close()

        if line.strip().startswith("DOGS"):
            return ".verdat"

        return ""

    def check_for_errors(self):
        if self.type in ["", ".verdat"]:
            try:
                verdat.check_valid_verdat(self)
                wx.MessageBox("This file is a valid verdat file.", "No Errors Found")
            except Exception, e:
                if hasattr(e, "points") and e.points != None:
                    self.clear_all_selections(STATE_FLAGGED)
                    for p in e.points:
                        self.select_point(p, STATE_FLAGGED)
                    app_globals.application.refresh()
                wx.MessageDialog(
                    app_globals.application.frame,
                    message=e.message,
                    caption="Verdat File Contains Errors",
                    style=wx.OK | wx.ICON_ERROR,
                ).ShowModal()

    def read_from_file(self, file_path):
        self.file_path = file_path
        (base, ext) = os.path.splitext(file_path)
        ext = ext.lower()
        file_types = [".xml", ".bna", ".verdat", ".dat", ".png", ".kap", ".tif"]
        file_type = ""
        if ext in file_types:
            file_type = ext
        else:
            file_type = self.guess_type_from_file_contents(file_path)

        if (file_type == ".xml"):
            app_globals.layer_manager.load_xml_layer(file_path)
            return

        elif (file_type == ".bna"):
            (self.load_error_string,
             f_polygon_points,
             f_polygon_starts,
             f_polygon_counts,
             f_polygon_types,
             f_polygon_identifiers) = File_loader.load_bna_file(file_path)

            if (self.load_error_string == ""):
                self.determine_layer_color()
                self.type = ext
                self.labels_visible = False
                n_points = np.alen(f_polygon_points)
                n_polygons = np.alen(f_polygon_starts)
                if (n_points > 0):
                    self.points_visible = False
                    self.points = self.make_points(n_points)
                    self.points.view(self.POINT_XY_VIEW_DTYPE).xy[
                        0: n_points
                    ] = f_polygon_points
                    self.polygons = self.make_polygons(n_polygons)
                    self.polygons.start[
                        0: n_polygons
                    ] = f_polygon_starts
                    self.polygons.count[
                        0: n_polygons
                    ] = f_polygon_counts
                    # TODO: for now we assume each polygon is its own group
                    self.polygons.group = np.arange(n_polygons)
                    self.polygon_adjacency_array = self.make_polygon_adjacency_array(n_points)
                    total = 0
                    for p in xrange(n_polygons):
                        c = self.polygons.count[p]
                        self.polygon_adjacency_array.polygon[total: total + c] = p
                        self.polygon_adjacency_array.next[total: total + c] = np.arange(total + 1, total + c + 1)
                        self.polygon_adjacency_array.next[total + c - 1] = total
                        total += c

                    green = color_to_int(0.25, 0.5, 0, 0.75)
                    blue = color_to_int(0.0, 0.0, 0.5, 0.75)
                    gray = color_to_int(0.5, 0.5, 0.5, 0.75)
                    # the following "fancy indexing" relies on these particular values in f_polygon_types
                    # BNA_LAND_FEATURE_CODE = 1
                    # BNA_WATER_FEATURE_CODE = 2
                    # BNA_OTHER_FEATURE_CODE = 3
                    color_array = np.array((0, green, blue, gray), dtype=np.uint32)
                    self.polygons.color = color_array[np.clip(f_polygon_types, 1, 3)]
                    """
                    def map_type_to_color( t ):
                        if ( t == File_loader.BNA_LAND_FEATURE_CODE ):
                            return green
                        elif ( t == File_loader.BNA_WATER_FEATURE_CODE ):
                            return blue
                        else:
                            return gray
                    self.polygons.color = np.vectorize( map_type_to_color )( f_polygon_types )
                    """

                    self.points.state = 0

        elif (file_type in [".verdat", ".dat"]):
            (self.load_error_string,
             f_points,
             f_depths,
             f_line_segment_indexes,
             self.depth_unit) = File_loader.load_verdat_file(file_path)
            if (self.load_error_string == ""):
                self.type = ext
                n = np.alen(f_points)
                if (n > 0):
                    self.determine_layer_color()
                    self.points = self.make_points(n)
                    self.points.view(self.POINT_XY_VIEW_DTYPE).xy[
                        0: n
                    ] = f_points
                    self.points.z[
                        0: n
                    ] = f_depths
                    self.points.color = self.color
                    self.points.state = 0

                    n = np.alen(f_line_segment_indexes)
                    self.line_segment_indexes = self.make_line_segment_indexes(n)
                    self.line_segment_indexes.view(self.LINE_SEGMENT_POINTS_VIEW_DTYPE).points[
                        0: n
                    ] = f_line_segment_indexes
                    self.line_segment_indexes.color = self.color
                    self.line_segment_indexes.state = 0

        else:
            (self.load_error_string,
             self.images,
             self.image_sizes,
             self.image_world_rects,
             projection) = File_loader.load_image_file(file_path)

            if (self.load_error_string == ""):
                self.type = ext

                # change the app projection to latlong if this image is latlong projection
                # and we don't currently have a mercator image loaded;
                # alternatively, if we are in latlong and we don't currently have
                # a latlong image loaded, and this image is mercator, change to mercator

                # TODO: handle other projections besides +proj=merc and +proj=longlat
                raster_layers = app_globals.layer_manager.count_raster_layers()
                vector_layers = app_globals.layer_manager.count_vector_layers()
                if raster_layers == 0 and vector_layers == 0:
                    pub.sendMessage(('layer', 'proejction', 'changed'), layer=self, projection=projection.srs)
                currently_merc = app_globals.application.renderer.projection.srs.find("+proj=merc") != -1
                currently_longlat = app_globals.application.renderer.projection.srs.find("+proj=longlat") != -1
                incoming_merc = projection.srs.find("+proj=merc") != -1
                incoming_longlat = projection.srs.find("+proj=longlat") != -1

                disagreement = (currently_merc != incoming_merc) or (currently_longlat != incoming_longlat)
                if (disagreement):
                    if (incoming_merc):
                        type = "Mercator"
                        srs = "+proj=merc +units=m +over"
                    else:
                        type = "Longitude/Latitude"
                        srs = "+proj=longlat +over"
                    message = None
                    if (raster_layers > 0):
                        message = "The file you are loading is in " + type + " projection, but one or more other raster files already loaded have a different projection. Do you want to load this file anyway, with distortion?"
                    elif (vector_layers > 0):
                        message = "The file you are loading is in " + type + " projection. Would you like to convert the loaded vector data to this projection?"

                    if message is not None:
                        dialog = wx.MessageDialog(
                            app_globals.application.frame,
                            message=message,
                            caption="Projection Conflict",
                            style=wx.OK | wx.CANCEL | wx.ICON_QUESTION,
                        )

                        if (dialog.ShowModal() != wx.ID_OK):
                            self.load_error_string = "Projection conflict"
                            #
                            return

                        pub.sendMessage(('layer', 'proejction', 'changed'), layer=self, projection=srs)

        if (self.load_error_string == ""):
            self.bounds = self.compute_bounding_rect()
            pub.sendMessage(('layer', 'loaded'), layer=self)

    def make_points(self, count):
        return np.repeat(
            np.array([(np.nan, np.nan, np.nan, 0, 0)], dtype=self.POINT_DTYPE),
            count,
        ).view(np.recarray)

    def make_line_segment_indexes(self, count):
        return np.repeat(
            np.array([(0, 0, 0, 0)], dtype=self.LINE_SEGMENT_DTYPE),
            count,
        ).view(np.recarray)

    def make_triangles(self, count):
        return np.repeat(
            np.array([(0, 0, 0, 0, 0)], dtype=self.TRIANGLE_DTYPE),
            count,
        ).view(np.recarray)

    def make_polygons(self, count):
        return np.repeat(
            np.array([(0, 0, 0, 0, 0)], dtype=self.POLYGON_DTYPE),
            count,
        ).view(np.recarray)

    def make_polygon_adjacency_array(self, count):
        return np.repeat(
            np.array([(0, 0)], dtype=self.POLYGON_ADJACENCY_DTYPE),
            count,
        ).view(np.recarray)

    def determine_layer_color(self):
        if not self.color:
            print "setting layer color?"
            self.color = DEFAULT_COLORS[
                Layer.next_default_color_index
            ]

            Layer.next_default_color_index = (
                Layer.next_default_color_index + 1
            ) % len(DEFAULT_COLORS)

    def compute_bounding_rect(self, mark_type=STATE_NONE):
        bounds = rect.NONE_RECT

        if (self.points != None):
            if (mark_type == STATE_NONE):
                points = self.points
            else:
                points = self.points[self.get_selected_point_indexes(mark_type)]
            l = points.x.min()
            r = points.x.max()
            b = points.y.min()
            t = points.y.max()
            bounds = rect.accumulate_rect(bounds, ((l, b), (r, t)))

        if (self.triangle_points != None):
            l = self.triangle_points.x.min()
            r = self.triangle_points.x.max()
            b = self.triangle_points.y.min()
            t = self.triangle_points.y.max()
            bounds = rect.accumulate_rect(bounds, ((l, b), (r, t)))

        if (self.image_world_rects != None):
            world_rect_flat_list = flatten(self.image_world_rects)
            b = world_rect_flat_list[0]
            for r in world_rect_flat_list[1:]:
                b = rect.accumulate_rect(b, r)
            bounds = rect.accumulate_rect(bounds, b)

        return bounds

    def clear_all_selections(self, mark_type=STATE_SELECTED):
        self.clear_all_point_selections(mark_type)
        self.clear_all_line_segment_selections(mark_type)
        self.clear_all_polygon_selections(mark_type)
        self.increment_change_count()

    def clear_all_point_selections(self, mark_type=STATE_SELECTED):
        if (self.points != None):
            self.points.state = self.points.state & (0xFFFFFFFF ^ mark_type)
            self.increment_change_count()

    def clear_all_line_segment_selections(self, mark_type=STATE_SELECTED):
        if (self.line_segment_indexes != None):
            self.line_segment_indexes.state = self.line_segment_indexes.state & (0xFFFFFFFF ^ mark_type)
            self.increment_change_count()

    def clear_all_polygon_selections(self, mark_type=STATE_SELECTED):
        if (self.polygons != None):
            self.polygons.state = self.polygons.state & (0xFFFFFFFF ^ mark_type)
            self.increment_change_count()

    def has_points(self):
        return self.points is not None and len(self.points) > 0

    def select_point(self, point_index, mark_type=STATE_SELECTED):
        self.points.state[point_index] = self.points.state[point_index] | mark_type
        self.increment_change_count()

    def deselect_point(self, point_index, mark_type=STATE_SELECTED):
        self.points.state[point_index] = self.points.state[point_index] & (0xFFFFFFFF ^ mark_type)
        self.increment_change_count()

    def is_point_selected(self, point_index, mark_type=STATE_SELECTED):
        return self.points != None and (self.points.state[point_index] & mark_type) != 0

    def select_line_segment(self, line_segment_index, mark_type=STATE_SELECTED):
        self.line_segment_indexes.state[line_segment_index] = self.line_segment_indexes.state[line_segment_index] | mark_type
        self.increment_change_count()

    def deselect_line_segment(self, line_segment_index, mark_type=STATE_SELECTED):
        self.line_segment_indexes.state[line_segment_index] = self.line_segment_indexes.state[line_segment_index] & (0xFFFFFFFF ^ mark_type)
        self.increment_change_count()

    def is_line_segment_selected(self, line_segment_index, mark_type=STATE_SELECTED):
        return self.line_segment_indexes != None and (self.line_segment_indexes.state[line_segment_index] & mark_type) != 0

    def select_polygon(self, polygon_index, mark_type=STATE_SELECTED):
        self.polygons.state[polygon_index] = self.polygons.state[polygon_index] | mark_type
        self.increment_change_count()

    def deselect_polygon(self, polygon_index, mark_type=STATE_SELECTED):
        self.polygons.state[polygon_index] = self.polygons.state[polygon_index] & (0xFFFFFFFF ^ mark_type)
        self.increment_change_count()

    def is_polygon_selected(self, polygon_index, mark_type=STATE_SELECTED):
        return self.polygons != None and (self.polygons.state[polygon_index] & mark_type) != 0

    def select_points(self, indexes, mark_type=STATE_SELECTED):
        self.points.state[indexes] |= mark_type
        self.increment_change_count()

    def select_points_in_rect(self, is_toggle_mode, is_add_mode, w_r, mark_type=STATE_SELECTED):
        if (not is_toggle_mode and not is_add_mode):
            self.clear_all_point_selections()
        indexes = np.where(np.logical_and(
            np.logical_and(self.points.x >= w_r[0][0], self.points.x <= w_r[1][0]),
            np.logical_and(self.points.y >= w_r[0][1], self.points.y <= w_r[1][1])))
        if (is_add_mode):
            self.points.state[indexes] |= mark_type
        if (is_toggle_mode):
            self.points.state[indexes] ^= mark_type
        self.increment_change_count()

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

    def get_selected_point_indexes(self, mark_type=STATE_SELECTED):
        if (self.points == None):
            return []
        #
        return np.where((self.points.state & mark_type) != 0)[0]

    def get_selected_point_plus_line_point_indexes(self, mark_type=STATE_SELECTED):
        indexes = np.arange(0)
        if (self.points != None):
            indexes = np.append(indexes, self.get_selected_point_indexes(mark_type))
        if (self.line_segment_indexes != None):
            l_s_i_s = self.get_selected_line_segment_indexes(mark_type)
            indexes = np.append(indexes, self.line_segment_indexes[l_s_i_s].point1)
            indexes = np.append(indexes, self.line_segment_indexes[l_s_i_s].point2)
        #
        return np.unique(indexes)

    def get_selected_line_segment_indexes(self, mark_type=STATE_SELECTED):
        if (self.line_segment_indexes == None):
            return []
        #
        return np.where((self.line_segment_indexes.state & mark_type) != 0)[0]

    def get_selected_polygon_indexes(self, mark_type=STATE_SELECTED):
        if (self.polygons == None):
            return []
        #
        return np.where((self.polygons.state & mark_type) != 0)[0]

    def get_num_points_selected(self, mark_type=STATE_SELECTED):
        return len(self.get_selected_point_indexes(mark_type))

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

    def offset_selected_objects(self, world_d_x, world_d_y):
        self.offset_selected_points(world_d_x, world_d_y)
        self.offset_selected_polygons(world_d_x, world_d_y)

    def offset_selected_points(self, world_d_x, world_d_y):
        if (self.points != None):
            # offset our own copy of the points (which automatically updates our own line segments)
            s_p_i_s = self.get_selected_point_plus_line_point_indexes()
            for point_index in s_p_i_s:
                self.offset_point(point_index, world_d_x, world_d_y, True)
            # self.offset_points( s_p_i_s, world_d_x, world_d_y, True )
            pub.sendMessage(('layer', 'points', 'changed'), layer=self)
            self.increment_change_count()

    def offset_point(self, point_index, world_d_x, world_d_y, add_undo_info=False):
        self.points.x[point_index] += world_d_x
        self.points.y[point_index] += world_d_y
        """
        # we don't set the undo information here because this function is called repeatedly as the mouse moves
        if ( add_undo_info ):
            params = ( world_d_x, world_d_y )
            app_globals.editor.add_undo_operation_to_operation_batch( OP_MOVE_POINT, self, point_index, params )
        """

    """
    def rebuild_for_offset_points( self ):
        if ( self.line_segment_indexes != None ):
            self.point_and_line_set_renderer.build_line_segment_buffers(
                self.points.view( self.POINT_XY_VIEW_DTYPE ).xy,
                self.line_segment_indexes.view( self.LINE_SEGMENT_POINTS_VIEW_DTYPE )[ "points" ],
                None )
        self.point_and_line_set_renderer.reproject( self.points.view( self.POINT_XY_VIEW_DTYPE ).xy,
                                                    app_globals.application.renderer.projection,
                                                    app_globals.application.renderer.projection_is_identity )
    """

    def offset_selected_polygons(self, world_d_x, world_d_y):
        self.increment_change_count()

    def delete_all_selected_objects(self):
        point_indexes = self.get_selected_point_indexes()
        l_s_i_s = None
        if (self.get_selected_line_segment_indexes != None):
            l_s_i_s = self.get_selected_line_segment_indexes()
        if ((point_indexes != None and len(point_indexes)) > 0 or (l_s_i_s != None and len(l_s_i_s) > 0)):
            self.delete_points_and_lines(point_indexes, l_s_i_s, True)
        self.increment_change_count()

    def delete_points_and_lines(self, point_indexes, l_s_i_s, add_undo_info):
        line_segment_indexes_to_be_deleted = None
        if (self.line_segment_indexes != None):
            # (1) delete any lines whose points are going away
            line_segment_indexes_to_be_deleted = np.where(np.in1d(self.line_segment_indexes.point1, point_indexes))
            line_segment_indexes_to_be_deleted = np.append(line_segment_indexes_to_be_deleted, np.where(np.in1d(self.line_segment_indexes.point2, point_indexes)))
            line_segment_indexes_to_be_deleted = np.unique(line_segment_indexes_to_be_deleted)
            # (2) add in the line segments that are being deleted explicitly
            if (l_s_i_s != None):
                line_segment_indexes_to_be_deleted = np.unique(np.append(line_segment_indexes_to_be_deleted, l_s_i_s))

            if (add_undo_info):
                # add everything to the undo stack in an order such that if it was undone from last to first it would all work
                l = list(line_segment_indexes_to_be_deleted)
                l.reverse()
                for i in l:
                    params = (self.line_segment_indexes.point1[i], self.line_segment_indexes.point2[i], self.line_segment_indexes.color[i], self.line_segment_indexes.state[i])
                    app_globals.editor.add_undo_operation_to_operation_batch(OP_DELETE_LINE, self, i, params)

            # adjust the point indexes of the remaining line segments
            offsets = np.zeros(np.alen(self.line_segment_indexes))
            for index in point_indexes:
                offsets += np.where(self.line_segment_indexes.point1 > index, 1, 0)
            self.line_segment_indexes.point1 -= offsets
            offsets[: np.alen(offsets)] = 0
            for index in point_indexes:
                offsets += np.where(self.line_segment_indexes.point2 > index, 1, 0)
            self.line_segment_indexes.point2 -= offsets

        if (add_undo_info):
            # add everything to the undo stack in an order such that if it was undone from last to first it would all work
            l = list(point_indexes)
            l.reverse()
            for i in l:
                params = ((self.points.x[i], self.points.y[i]), self.points.z[i], self.points.color[i], self.points.state[i])
                app_globals.editor.add_undo_operation_to_operation_batch(OP_DELETE_POINT, self, i, params)

        # delete them from the layer
        self.points = np.delete(self.points, point_indexes, 0)
        if (line_segment_indexes_to_be_deleted != None):
            # then delete the line segments
            self.line_segment_indexes = np.delete(self.line_segment_indexes, line_segment_indexes_to_be_deleted, 0)

        # delete them from the point_and_line_set_renderer (by simply rebuilding it)

        """
        # delete them from the label_set_renderer
        if ( self.label_set_renderer != None ):
            self.label_set_renderer.delete_points( point_indexes )
            self.label_set_renderer.reproject( self.points.view( self.POINT_XY_VIEW_DTYPE ).xy,
                                               app_globals.application.renderer.projection,
                                               app_globals.application.renderer.projection_is_identity )
        """

        # when points are deleted from a layer the indexes of the points in the existing merge dialog box
        # become invalid; so force the user to re-find duplicates in order to create a valid list again
        pub.sendMessage(('layer', 'points', 'deleted'), layer=self)

    def insert_point(self, world_point):
        return self.insert_point_at_index(len(self.points), world_point, self.default_depth, self.color, STATE_SELECTED, True)

    def insert_point_at_index(self, point_index, world_point, z, color, state, add_undo_info):
        t0 = time.clock()
        # insert it into the layer
        p = np.array([(world_point[0], world_point[1], z, color, state)],
                     dtype=self.POINT_DTYPE)
        if (self.points == None):
            self.points = self.make_points(1)
            self.points[0] = p
            point_index = 0
            pub.sendMessage(('layer', 'updated'), layer=self)
            app_globals.application.refresh()
            app_globals.application.layer_tree_control.select_layer(self)
        else:
            self.points = np.insert(self.points, point_index, p).view(np.recarray)
        t = time.clock() - t0  # t is wall seconds elapsed (floating point)
        # print "inserted new point in {0} seconds".format( t )

        # update point indexes in the line segements to account for the inserted point
        if (self.line_segment_indexes != None):
            offsets = np.zeros(np.alen(self.line_segment_indexes))
            offsets += np.where(self.line_segment_indexes.point1 >= point_index, 1, 0)
            self.line_segment_indexes.point1 += offsets
            offsets[: np.alen(offsets)] = 0
            offsets += np.where(self.line_segment_indexes.point2 >= point_index, 1, 0)
            self.line_segment_indexes.point2 += offsets

        if (add_undo_info):
            params = ((self.points.x[point_index], self.points.y[point_index]), self.points.z[point_index], self.points.color[point_index], self.points.state[point_index])
            app_globals.editor.add_undo_operation_to_operation_batch(OP_ADD_POINT, self, point_index, params)

        # insert it into the point_and_line_set_renderer (by simply rebuilding it)
        # we don't update the point_and_line_set_renderer if not adding undo info, because that means we are undoing or redoing
        # and the point_and_line_set_renderer for all affected layers will get rebuilt at the end of the process
        if (add_undo_info):
            pub.sendMessage(('layer', 'points', 'changed'), layer=self)

        """
        t0 = time.clock()
        # insert it into the label_set_renderer
        if ( self.label_set_renderer != None ):
            self.label_set_renderer.insert_point( len( self.points ) - 1,
                                                  str( self.default_depth ),
                                                  world_point,
                                                  app_globals.application.renderer.projection,
                                                  app_globals.application.renderer.projection_is_identity )
        t = time.clock() - t0 # t is wall seconds elapsed (floating point)
        print "inserted into label set renderer in {0} seconds".format( t )
        """

        return point_index

    def insert_point_in_line(self, world_point, line_segment_index):
        new_point_index = self.insert_point(world_point)
        point_index_1 = self.line_segment_indexes.point1[line_segment_index]
        point_index_2 = self.line_segment_indexes.point2[line_segment_index]
        color = self.line_segment_indexes.color[line_segment_index]
        state = self.line_segment_indexes.state[line_segment_index]
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
                                dtype = self.LINE_SEGMENT_DTYPE ).view( np.recarray )
                self.line_segment_indexes = np.append( self.line_segment_indexes, l_s ).view( np.recarray )
                num_connections_made += 1
        if ( num_connections_made > 0 ):
            self.rebuild_point_and_line_set_renderer()
    """

    def insert_line_segment(self, point_index_1, point_index_2):
        return self.insert_line_segment_at_index(len(self.line_segment_indexes), point_index_1, point_index_2, self.color, STATE_NONE, True)

    def insert_line_segment_at_index(self, l_s_i, point_index_1, point_index_2, color, state, add_undo_info):
        l_s = np.array([(point_index_1, point_index_2, color, state)],
                       dtype=self.LINE_SEGMENT_DTYPE).view(np.recarray)
        self.line_segment_indexes = np.insert(self.line_segment_indexes, l_s_i, l_s).view(np.recarray)

        if (add_undo_info):
            params = (self.line_segment_indexes.point1[l_s_i], self.line_segment_indexes.point2[l_s_i], self.line_segment_indexes.color[l_s_i], self.line_segment_indexes.state[l_s_i])
            app_globals.editor.add_undo_operation_to_operation_batch(OP_ADD_LINE, self, l_s_i, params)

        # we don't update the point_and_line_set_renderer if not adding undo info, because that means we are undoing or redoing
        # and the point_and_line_set_renderer for all affected layers will get rebuilt at the end of the process
        if (add_undo_info):
            pub.sendMessage(('layer', 'lines', 'changed'), layer=self)

        return l_s_i

    def delete_point(self, point_index, add_undo_info):
        if (self.find_points_connected_to_point(point_index) != []):
            raise Exception()

        if (add_undo_info):
            params = ((self.points.x[point_index], self.points.y[point_index]), self.points.z[point_index], self.points.color[point_index], self.points.state[point_index])
            app_globals.editor.add_undo_operation_to_operation_batch(OP_DELETE_POINT, self, point_index, params)
        self.points = np.delete(self.points, point_index, 0)

        # update point indexes in the line segements to account for the deleted point
        if (self.line_segment_indexes != None):
            offsets = np.zeros(np.alen(self.line_segment_indexes))
            offsets += np.where(self.line_segment_indexes.point1 > point_index, 1, 0)
            self.line_segment_indexes.point1 -= offsets
            offsets[: np.alen(offsets)] = 0
            offsets += np.where(self.line_segment_indexes.point2 > point_index, 1, 0)
            self.line_segment_indexes.point2 -= offsets

        pub.sendMessage(('layer', 'points', 'deleted'), layer=self)

    def delete_line_segment(self, l_s_i, add_undo_info):
        if (add_undo_info):
            params = (self.line_segment_indexes.point1[l_s_i], self.line_segment_indexes.point2[l_s_i], self.line_segment_indexes.color[l_s_i], self.line_segment_indexes.state[l_s_i])
            app_globals.editor.add_undo_operation_to_operation_batch(OP_DELETE_LINE, self, l_s_i, params)
        self.line_segment_indexes = np.delete(self.line_segment_indexes, l_s_i, 0)

    def triangulate(self, q, a):
        # determine the boundaries in this layer
        self.determine_layer_color()
        (boundaries, non_boundary_points) = find_boundaries(
            points=self.points,
            point_count=len(self.points),
            lines=self.line_segment_indexes,
            line_count=len(self.line_segment_indexes))

        # calculate a hole point for each boundary
        hole_points_xy = np.empty(
            (len(boundaries), 2), np.float32,
        )

        for (boundary_index, (boundary, area)) in enumerate(boundaries):
            if (len(boundary) < 3):
                continue

            # the "hole" point for the outer boundary (first in the list) should be outside of it
            if boundary_index == 0:
                hole_points_xy[boundary_index] = generate_outside_hole_point(boundary, self.points)
            else:
                hole_points_xy[boundary_index] = generate_inside_hole_point(boundary, self.points)

        params = "V"
        if (q is not None):
            params = params + "q" + str(q)
        if (a is not None):
            params = params + "a" + str(a)

        # we need to use projected points for the triangulation
        projected_points = self.points.view(self.POINT_XY_VIEW_DTYPE).xy[: len(self.points)].view(np.float32).copy()
        if (app_globals.application.renderer.projection_is_identity):
            projected_points[:, 0] = self.points[:, 0]
            projected_points[:, 1] = self.points[:, 1]
        else:
            projected_points[:, 0], projected_points[:, 1] = app_globals.application.renderer.projection(self.points.x, self.points.y)
            hole_points_xy[:, 0], hole_points_xy[:, 1] = app_globals.application.renderer.projection(hole_points_xy[:, 0], hole_points_xy[:, 1])
        print "params: " + params
        print "hole points:"
        print hole_points_xy
        (triangle_points_xy,
         triangle_points_z,
         triangle_line_segment_indexes,  # not needed
         triangles) = triangulate_simple(
            params,
            projected_points,
            self.points.z[: len(self.points)].copy(),
            self.line_segment_indexes.view(self.LINE_SEGMENT_POINTS_VIEW_DTYPE).points[: len(self.line_segment_indexes)].view(np.uint32).copy(),
            hole_points_xy)

        self.triangle_points = self.make_points(len(triangle_points_xy))
        self.triangle_points.view(self.POINT_XY_VIEW_DTYPE).xy[
            0: len(triangle_points_xy)
        ] = triangle_points_xy
        self.triangle_points[0: len(triangle_points_xy)].z = triangle_points_z
        self.triangle_points.color = self.color

        # now un-project the points
        if (not app_globals.application.renderer.projection_is_identity):
            # import code; code.interact( local = locals() )
            self.triangle_points.x, self.triangle_points.y = app_globals.application.renderer.projection(self.triangle_points.x, self.triangle_points.y, inverse=True)

        self.triangles = self.make_triangles(len(triangles))
        self.triangles.view(self.TRIANGLE_POINTS_VIEW_DTYPE).point_indexes = triangles

        pub.sendMessage(('layer', 'triangulated'), layer=self)

    def merge_from_source_layers(self, layer_a, layer_b):
        # for now we only handle merging of points and lines

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

        pub.sendMessage(('layer', 'updated'), layer=self)

    # returns a list of pairs of point indexes
    def find_duplicates(self, distance_tolerance_degrees, depth_tolerance_percentage=-1):
        if (self.points == None or len(self.points) < 2):
            return []

        points = self.points.view(
            self.POINT_XY_VIEW_DTYPE
        ).xy[:].copy()

        latlong_proj = Projection("+proj=latlong")

        # If necessary, convert points to lat-long before find duplicates.
        # This makes the distance tolerance work properly.
        projection = app_globals.application.renderer.projection
        if projection.srs != latlong_proj.srs:
            points = points.view(
                [("x", np.float32), ("y", np.float32)]
            ).view(np.recarray)
            latlong_proj.transform_many(
                points, points, projection, set_cache=False
            )

        # cKDTree doesn't handle NaNs gracefully, but it does handle infinity
        # values. So replace all the NaNs with infinity.
        points = points.view(np.float32)
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

        app_globals.application.refresh()

    def increment_change_count(self):
        self.change_count += 1
        if (self.change_count == sys.maxint):
            self.change_count = 0

    def destroy(self):
        app_globals.editor.delete_undo_operations_for_layer(self)
