import collections

import wx
import wx.adv
import numpy as np
import numpy.random as rand

from . import builtin_discrete_colormaps, builtin_continuous_colormaps, get_colormap, DiscreteColormap, user_defined_discrete_colormaps, ListedBoundedColormap
from ...ui.buttons import ColorSelectButton, EVT_COLORSELECT

import logging
log = logging.getLogger(__name__)


class ColormapImage(object):
    def __init__(self, width, height):
        self.arrow_width = 20
        self.height = height
        self.create_image_array(width)

    def create_image_array(self, width):
        self.width = width
        self.array = np.empty((self.height, width, 3), dtype='uint8')
        self.image = wx.ImageFromBuffer(width, self.height, self.array)

    def calc_bitmap(self, colormap, width=None, bgcolor=(255, 255, 255)):
        if width is not None:
            if width != self.width:
                self.create_image_array(width)
        if colormap.is_discrete:
            bgcolor = bgcolor[0:3]
            middle_width = self.width - 2 * self.arrow_width
            middle = colormap.calc_rgb_texture(middle_width)
            self.array[:,self.arrow_width:-self.arrow_width,:] = middle
            self.array[:,0:self.arrow_width,:] = np.asarray(colormap.under_rgba[0:3], dtype=np.float32) * 255
            self.array[:,-self.arrow_width:,:] = np.asarray(colormap.over_rgba[0:3], dtype=np.float32) * 255
            half_height = self.height // 2
            for h in range(half_height):
                w = self.arrow_width * h * 2 // self.height
                self.array[half_height - h - 1,0:w,:] = bgcolor
                self.array[self.height - half_height + h,0:w,:] = bgcolor
                self.array[half_height - h - 1,self.width-w:,:] = bgcolor
                self.array[self.height - half_height + h,self.width-w:,:] = bgcolor
        else:
            colors = colormap.calc_rgb_texture(self.width)
            self.array[:,:,:] = colors
        return wx.Bitmap(self.image)


class ColormapComboBox(wx.adv.OwnerDrawnComboBox):
    def __init__(self, *args, **kwargs):
        # self.known_colormaps = dict(builtin_discrete_colormaps)
        popup_width = kwargs.pop('popup_width', 300)
        self.custom = kwargs.pop('custom_colormaps', {})  # name:colormap
        # if self.custom:
        #     self.known_colormaps.update(self.custom)
        # print self.known_colormaps
        self.recalc_order()
        kwargs['choices'] = self.colormap_name_order
        kwargs['style'] = wx.CB_READONLY
        # self.start_builtin_index = len(self.custom)
        wx.adv.OwnerDrawnComboBox.__init__(self, *args, **kwargs)

        self.height = 20
        self.control_image = ColormapImage(popup_width, self.height)
        self.dropdown_image = ColormapImage(popup_width, self.height)
        dc = wx.MemoryDC()
        self.char_height = dc.GetCharHeight()
        self.internal_spacing = 2
        self.item_height = self.height + self.char_height + 2 * self.internal_spacing
        self.bitmap_x = self.internal_spacing
        self.bitmap_y = self.char_height + self.internal_spacing

        self.SetPopupMinWidth(popup_width)

    def recalc_order(self):
        self.colormap_name_order = sorted(user_defined_discrete_colormaps.keys()) + sorted(builtin_discrete_colormaps.keys()) + sorted(builtin_continuous_colormaps.keys())
        self.discrete_start = 0
        self.continuous_start = len(builtin_discrete_colormaps)

    def rebuild_colormap_list(self):
        self.recalc_order()

    def index_of(self, name):
        return self.colormap_name_order.index(name)

    def set_selection_by_name(self, name):
        try:
            index = self.index_of(name)
        except ValueError:
            return
        self.SetSelection(index)
        self.override_control_colormap = None

    def get_selected_name(self):
        index = self.GetSelection()
        return self.colormap_name_order[index]

    # Overridden from OwnerDrawnComboBox, called to draw each
    # item in the list
    def OnDrawItem(self, dc, rect, item, flags):
        if item == wx.NOT_FOUND:
            # painting the control, but there is no valid item selected yet
            return

        r = wx.Rect(*rect)  # make a copy

        name = self.colormap_name_order[item]
        c = get_colormap(name)
        if flags & wx.adv.ODCB_PAINTING_CONTROL:
            width = r.width - 2 * self.internal_spacing
            x = self.internal_spacing
            y = (r.height - self.height) // 2
            b = self.control_image.calc_bitmap(c, width, self.GetParent().GetBackgroundColour())
            dc.DrawBitmap(b, r.x + x, r.y + y)
        else:
            width = r.width - 2 * self.internal_spacing
            b = self.dropdown_image.calc_bitmap(c, width, self.GetParent().GetBackgroundColour())
            dc.DrawBitmap(b, r.x + self.bitmap_x, r.y + self.bitmap_y)
            dc.DrawText(c.name, r.x + self.bitmap_x, r.y)

    # Overridden from OwnerDrawnComboBox, called for drawing the
    # background area of each item.
    def OnDrawBackground(self, dc, rect, item, flags):
        # If the item is selected, or its item # iseven, or we are painting the
        # combo control itself, then use the default rendering.
        if (flags & wx.adv.ODCB_PAINTING_CONTROL):
            flags = flags & ~(wx.adv.ODCB_PAINTING_CONTROL | wx.adv.ODCB_PAINTING_SELECTED)
        wx.adv.OwnerDrawnComboBox.OnDrawBackground(self, dc, rect, item, flags)

    # Overridden from OwnerDrawnComboBox, should return the height
    # needed to display an item in the popup, or -1 for default
    def OnMeasureItem(self, item):
        return self.item_height

    # Overridden from OwnerDrawnComboBox.  Callback for item width, or
    # -1 for default/undetermined
    def OnMeasureItemWidth(self, item):
        return self.item_width


class DiscreteOnlyColormapComboBox(ColormapComboBox):
    def recalc_order(self):
        self.colormap_name_order = sorted(user_defined_discrete_colormaps.keys()) + sorted(builtin_discrete_colormaps.keys())


class ColormapEntry(wx.Panel):
    label_text = "Bin Boundary"

    def __init__(self, parent, num, dialog):
        wx.Panel.__init__(self, parent, -1, name="panel#%d" % num)
        self.entry_num = num
        self.dialog = dialog
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.color = ColorSelectButton(self, -1, "", (0, 0, 0), size=(100, 20))
        self.color.Bind(EVT_COLORSELECT, self.on_color_changed)
        hbox.Add(self.color, 1, wx.EXPAND)
        self.sizer.Add(hbox, 0, wx.EXPAND)

        if num > 0:  # skip first entry which will be the over color
            self.text_box = wx.Panel(self, -1)
            hbox = wx.BoxSizer(wx.HORIZONTAL)
            b = wx.Button(self.text_box, -1, "+", style = wx.BU_NOTEXT | wx.BU_EXACTFIT)
            b.SetBitmapLabel(wx.ArtProvider.GetBitmap(wx.ART_PLUS, wx.ART_MENU))
            b.Bind(wx.EVT_BUTTON, self.on_add_entry)
            hbox.Add(b, 0, wx.ALIGN_CENTER_VERTICAL)
            self.label = wx.StaticText(self.text_box, -1, "%s (%%)" % (self.label_text))
            hbox.Add(self.label, 0, wx.ALIGN_CENTER_VERTICAL)
            self.text = wx.TextCtrl(self.text_box, -1, size=(100, 20))
            self.text.Bind(wx.EVT_TEXT, self.on_text_changed)
            hbox.Add(self.text, 1, wx.EXPAND)
            b = wx.Button(self.text_box, -1, "X", style = wx.BU_NOTEXT | wx.BU_EXACTFIT)
            b.SetBitmapLabel(wx.ArtProvider.GetBitmap(wx.ART_CLOSE, wx.ART_MENU))
            b.Bind(wx.EVT_BUTTON, self.on_remove_entry)
            hbox.Add(b, 0, wx.ALIGN_CENTER_VERTICAL)
            self.text_box.SetSizer(hbox)
            self.text_box.Layout()
            self.sizer.Add(self.text_box, 0, wx.EXPAND)

        self.Layout()

    def set_values(self, value, color, autoscale=True):
        if value is not None:
            self.text.ChangeValue(str(value))
            self.text.SetBackgroundColour("#FFFFFF")
            self.label.SetLabel("%s %s" % (self.label_text, "(%)" if autoscale else ""))
        int_colors = list((color * 255.0).astype(np.uint8))
        self.color.SetColor(int_colors)

    def on_add_entry(self, evt):
        self.dialog.add_entry(self.entry_num)

    def on_remove_entry(self, evt):
        self.dialog.remove_entry(self.entry_num)

    def on_text_changed(self, evt):
        try:
            num = float(self.text.GetValue())
            self.dialog.boundary_changed(self.entry_num, num)
            self.text.SetBackgroundColour("#FFFFFF")
        except ValueError:
            # it's not a float, or it overlaps a neighboring value
            self.text.SetBackgroundColour("#FF8080")

    def on_color_changed(self, evt):
        float_colors = np.asarray([float(c / 255.0) for c in evt.GetValue()], dtype=np.float32)
        self.dialog.set_color(self.entry_num, float_colors)


class DiscreteColormapDialog(wx.Dialog):
    def __init__(self, parent, current_colormap, values_min_max):
        wx.Dialog.__init__(self, parent, -1, "Edit Discrete Colormaps", size=(500, -1))
        self.bitmap_width = 300
        self.bitmap_height = 30
        self.working_copy = None
        self.values_min_max = values_min_max

        lsizer = wx.BoxSizer(wx.VERTICAL)

        s = wx.StaticText(self, -1, "Known colormaps:")
        lsizer.Add(s, 0, wx.EXPAND|wx.TOP, 10)
        self.colormap_list = DiscreteOnlyColormapComboBox(self, -1, "colormap_list", popup_width=300)
        self.colormap_list.Bind(wx.EVT_COMBOBOX, self.colormap_changed)
        self.colormap_list.SetSelection(0)
        lsizer.Add(self.colormap_list, 0, wx.EXPAND, 0)

        s = wx.StaticText(self, -1, "Current colormap:")
        lsizer.Add(s, 0, wx.EXPAND|wx.TOP, 40)

        self.colormap_name = wx.TextCtrl(self, -1, name="colormap_name")
        lsizer.Add(self.colormap_name, 0, wx.EXPAND, 5)

        self.control_image = ColormapImage(self.bitmap_width, self.bitmap_height)
        self.colormap_bitmap = wx.StaticBitmap(self, -1, name="colormap_bitmap", size=(self.bitmap_width, self.bitmap_height))
        lsizer.Add(self.colormap_bitmap, 0, wx.EXPAND, 5)

        if self.values_min_max is not None:
            b = wx.Button(self, -1, "Scale Bins to Current Data")
            b.Bind(wx.EVT_BUTTON, self.on_scale_data)
            lsizer.Add(b, 0, wx.CENTER|wx.TOP, 40)
            t = wx.StaticText(self, -1, "Bins will become fixed to the values you specify")
            lsizer.Add(t, 0, wx.ALL|wx.CENTER|wx.TOP, 2)

        b = wx.Button(self, -1, "Convert Bins to Percentages")
        b.Bind(wx.EVT_BUTTON, self.on_convert_bins_to_percentages)
        lsizer.Add(b, 0, wx.CENTER|wx.TOP, 40)
        t = wx.StaticText(self, -1, "Bins will scale to fit the range of data being viewed")
        lsizer.Add(t, 0, wx.ALL|wx.CENTER|wx.TOP, 2)

        # self.autoscale_button = wx.CheckBox(self, -1, "Automatically scale bins when switching view\nto new type of data")
        # self.autoscale_button.Bind(wx.EVT_CHECKBOX, self.on_autoscale)
        # lsizer.Add(self.autoscale_button, 0, wx.ALL|wx.CENTER|wx.TOP, 10)

        btnsizer = wx.StdDialogButtonSizer()
        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)
        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        lsizer.AddStretchSpacer(1)
        lsizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        rsizer = wx.BoxSizer(wx.VERTICAL)

        self.scrolled_param_panel =  wx.lib.scrolledpanel.ScrolledPanel(self, -1, name="param_panel", size=(400, 500))
        self.scrolled_param_panel.ShowScrollbars(False, True)
        self.scrolled_param_panel.SetAutoLayout(1)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.add_hi = wx.Button(self.scrolled_param_panel, -1, "Add Bin Above")
        self.add_hi.Bind(wx.EVT_BUTTON, self.on_add_above)
        sizer.Add(self.add_hi, 0, wx.ALL|wx.CENTER, 5)

        self.param_panel = wx.Panel(self.scrolled_param_panel, -1, name="param_panel")
        self.param_panel.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self.param_panel.GetSizer().AddStretchSpacer(1)
        self.panel_controls = []
        sizer.Add(self.param_panel, 1, wx.EXPAND, 0)

        self.add_lo = wx.Button(self.scrolled_param_panel, -1, "Add Bin Below")
        self.add_lo.Bind(wx.EVT_BUTTON, self.on_add_below)
        sizer.Add(self.add_lo, 0, wx.ALL|wx.CENTER, 5)
        self.scrolled_param_panel.SetSizer(sizer)

        rsizer.Add(self.scrolled_param_panel, 1, wx.EXPAND, 0)

        # rsizer.AddStretchSpacer(1)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(lsizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(rsizer, 1, wx.EXPAND|wx.ALL, 5)
        self.SetSizer(sizer)

        self.populate_panel(current_colormap.name)

    def populate_panel(self, name):
        try:
            d = get_colormap(name, True).copy()
        except KeyError:
            # not a valid discrete colormap name; start from the first item
            name = self.colormap_list.colormap_name_order[0]
            d = builtin_discrete_colormaps[name].copy()
        self.colormap_list.set_selection_by_name(name)
        self.colormap_name.SetValue(name)
        self.working_copy = d
        self.bin_borders = list(d.bin_borders)
        if d.autoscale:
            self.bin_borders = self.calc_percentages_of_bins()
        self.bin_colors = list(d.bin_colors)
        self.bin_borders[0:0] = [None]  # alternates color, val, color, val ... color
        self.update_panel_controls()

    def regenerate_colormap(self):
        log.debug("bin_borders(%d):%s" % (len(self.bin_borders), str(self.bin_borders)))
        log.debug("bin_colors(%d):%s" % (len(self.bin_colors), str(self.bin_colors)))
        name = self.colormap_name.GetValue()
        cmap = ListedBoundedColormap(self.bin_colors, name)
        values = self.bin_borders[1:]
        d = DiscreteColormap(name, cmap)
        d.set_values(values)
        d.autoscale = self.working_copy.autoscale
        self.working_copy = d

    def update_bitmap(self):
        self.regenerate_colormap()
        bitmap = self.control_image.calc_bitmap(self.working_copy, bgcolor=self.GetParent().GetBackgroundColour())
        self.colormap_bitmap.SetBitmap(bitmap)

    def create_panel_controls(self):
        autoscale = self.working_copy.autoscale
        for i, (val, color) in enumerate(zip(self.bin_borders, self.bin_colors)):
            try:
                c = self.panel_controls[i]
                if val is not None and not hasattr(c, 'text_box'):
                    raise IndexError
            except IndexError:
                c = ColormapEntry(self.param_panel, i, self)
                self.param_panel.GetSizer().Insert(0, c, 0, wx.EXPAND, 0)
                self.panel_controls.append(c)
            c.set_values(val, color, autoscale)
            c.Show()
        i += 1
        while i < len(self.panel_controls):
            self.panel_controls[i].Hide()
            i += 1
        self.param_panel.GetSizer().Layout()
        self.scrolled_param_panel.Layout()
        self.scrolled_param_panel.Fit()
        self.scrolled_param_panel.SetupScrolling(scroll_x=False, scrollToTop=False, scrollIntoView=True)
        self.Fit()
        self.Layout()

    def update_panel_controls(self):
        self.update_bitmap()
        self.create_panel_controls()

    def colormap_changed(self, evt):
        name = self.colormap_list.get_selected_name()
        self.populate_panel(name)

    def get_edited_colormap(self):
        self.working_copy.name += "prime"
        return self.working_copy

    def on_add_above(self, evt):
        log.debug("on_add_above: before: borders(%d):%s" % (len(self.bin_borders), str(self.bin_borders)))
        current = self.bin_borders[-1]
        if len(self.bin_borders) > 2:
            delta = current - self.bin_borders[-2]
            value = current + delta
        else:
            value = current + (0.1 * current)
        color = np.asarray([.5, .5, .5, 1.0], dtype=np.float32)
        self.bin_borders.append(value)
        self.bin_colors.append(color)
        log.debug("on_add_above: after: borders(%d):%s" % (len(self.bin_borders), str(self.bin_borders)))
        wx.CallAfter(self.update_panel_controls)

    def on_add_below(self, evt):
        current = self.bin_borders[1]
        if len(self.bin_borders) > 2:
            delta = current - self.bin_borders[2]
            value = current + delta
        else:
            value = current - (0.1 * current)
        color = np.asarray([.5, .5, .5, 1.0], dtype=np.float32)
        self.bin_borders[1:1] = [value]
        self.bin_colors[1:1] = [color]
        wx.CallAfter(self.update_panel_controls)

    def add_entry(self, entry_num):
        if entry_num == 1:  # first bin delimiter
            value = self.bin_borders[entry_num] - 1.0
        else:
            value = (self.bin_borders[entry_num] + self.bin_borders[entry_num - 1]) / 2.0
        color = np.asarray([.5, .5, .5, 1.0], dtype=np.float32)
        self.bin_borders[entry_num:entry_num] = [value]
        self.bin_colors[entry_num:entry_num] = [color]
        wx.CallAfter(self.update_panel_controls)

    def remove_entry(self, entry_num):
        self.bin_borders[entry_num:entry_num + 1] = []
        self.bin_colors[entry_num:entry_num + 1] = []
        wx.CallAfter(self.update_panel_controls)

    def boundary_changed(self, entry_num, val):
        if entry_num == 0:
            raise ValueError("How are you changing the hidden value?")
        if entry_num < len(self.bin_borders) - 1 and val >= self.bin_borders[entry_num + 1]:
            raise ValueError("%f is larger than next larger bin value %f" % (val, self.bin_borders[entry_num + 1]))
        if entry_num > 1 and val <= self.bin_borders[entry_num - 1]:
            raise ValueError("%f is larger than next smaller bin value %f" % (val, self.bin_borders[entry_num - 1]))
        self.bin_borders[entry_num] = val
        wx.CallAfter(self.update_bitmap)

    def set_color(self, entry_num, color):
        self.bin_colors[entry_num] = color
        wx.CallAfter(self.update_bitmap)

    def calc_percentages_of_bins(self):
        if self.bin_borders[0] is None:
            bins = self.bin_borders[1:]
        else:
            bins = self.bin_borders
        lo = min(bins)
        hi = max(bins)
        delta = hi - lo
        if delta == 0.0:
            hi = lo + 1.0
            delta = 1.0
        new_bins = [(v - lo) / delta for v in bins]
        return new_bins

    def on_scale_data(self, evt):
        # Rescale current colormap to match data instead of autoscaling when
        # map is loaded
        if self.values_min_max is None:
            log.debug("no min/max values specified when creating dialog box")
        else:
            temp = self.calc_percentages_of_bins()
            lo, hi = self.values_min_max
            if lo == hi:
                hi += 1.0
            delta = hi - lo
            self.bin_borders = [(v * delta) + lo for v in temp]
            self.bin_borders[0:0] = [None]  # Insert first dummy value
            self.working_copy.autoscale = False
            wx.CallAfter(self.update_panel_controls)

    def on_convert_bins_to_percentages(self, evt):
        # Revert the bins back to percentages based on the min/max values of
        # the bins
        self.bin_borders = self.calc_percentages_of_bins()
        self.bin_borders[0:0] = [None]  # Insert first dummy value
        self.working_copy.autoscale = True
        wx.CallAfter(self.update_panel_controls)
