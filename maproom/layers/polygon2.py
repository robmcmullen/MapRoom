import numpy as np

# Enthought library imports.
from traits.api import Any
from traits.api import Int
from traits.api import Str
from traits.api import Unicode

from ..library.scipy_ckdtree import cKDTree
from ..library.Boundary import Boundaries
from ..library.shapely_utils import shapely_to_polygon
from ..renderer import color_floats_to_int, data_types
from ..command import UndoInfo
from ..mouse_commands import DeleteLinesCommand, MergePointsCommand

from . import LineLayer, Folder, state

import logging
log = logging.getLogger(__name__)
progress_log = logging.getLogger("progress")


class PolygonBoundaryLayer(LineLayer):
    """Layer for points/lines/polygons.

    """
    name = "Polygon Boundary"

    type = "polygon_boundary"

    layer_info_panel = ["Point count", "Line segment count", "Flagged points", "Color"]

    selection_info_panel = ["Selected points", "Point index", "Point latitude", "Point longitude"]


class HoleLayer(LineLayer):
    """Layer for points/lines/polygons.

    """
    name = "Polygon Hole"

    type = "polygon_hole"

    layer_info_panel = ["Point count", "Line segment count", "Flagged points", "Color"]

    selection_info_panel = ["Selected points", "Point index", "Point latitude", "Point longitude"]


class PolygonParentLayer(Folder, LineLayer):
    """Parent folder for group of polygons. Direct children will be
    PolygonBoundaryLayer objects (with grandchildren will be HoleLayers) or
    PointLayer objects.

    """
    name = "Polygon"

    type = "polygon_folder"

    visibility_items = ["points", "lines", "labels"]

    layer_info_panel = ["Point count", "Line segment count", "Flagged points", "Color"]

    selection_info_panel = ["Selected points", "Point index", "Point latitude", "Point longitude"]

    @property
    def is_renderable(self):
        return True

    def has_groupable_objects(self):
        return True

    def get_info_panel_text(self, prop):
        if prop == "Point count":
            total = 0
            for child in self.get_child_layers():
                try:
                    total += len(self.points)
                except TypeError:
                    pass
            return str(total)
        elif prop == "Line segment count":
            total = 0
            for child in self.get_child_layers():
                try:
                    total += len(self.line_segment_indexes)
                except TypeError:
                    pass
            return str(total)
        return str(None)

    def rebuild_renderer(self, renderer, in_place=False):
        points = data_types.make_points(0)
        n_rings = 0
        ring_starts = []
        ring_counts = []
        point_start_index = 0
        for child in self.get_child_layers():
            if len(points) > 0:
                points = np.append(points, child.points).view(np.recarray)
            else:
                points = child.points.copy()
            n_rings += 1
            ring_starts.append(point_start_index)
            ring_counts.append(len(child.points))
            point_start_index += len(child.points)
        projection = self.manager.project.layer_canvas.projection
        projected_point_data = data_types.compute_projected_point_data(points, projection)
        renderer.set_points(projected_point_data, points.z, points.color.copy().view(dtype=np.uint8))
        self.rings, self.point_adjacency_array = data_types.compute_rings(ring_starts, ring_counts)
        print(f"ring list: {self.rings}")
        print(f"points: {point_start_index}, from rings: {self.rings[-1][0] + self.rings[-1][1]}")

        renderer.set_polygons(self.rings, self.point_adjacency_array)

    def can_render_for_picker(self, renderer):
        return renderer.canvas.project.layer_tree_control.is_edit_layer(self)

    def render_projected(self, renderer, w_r, p_r, s_r, layer_visibility, picker):
        log.log(5, "Rendering polygon folder layer!!! pick=%s" % (picker))
        if picker.is_active and not self.can_render_for_picker(renderer):
            return
        # the rings
        if layer_visibility["polygons"]:
            renderer.draw_polygons(self, picker,
                                   self.rings.color,
                                   color_floats_to_int(0, 0, 0, 1.0),
                                   1)
