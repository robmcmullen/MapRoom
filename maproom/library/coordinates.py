# coding=utf8
import re
import math

from .lat_lon_parser import parse, to_deg_min, to_deg_min_sec


def haversine(lon1, lat1, lon2=None, lat2=None, r=6371.0):
    if lon2 is None:
        lon2, lat2 = lat1[0], lat1[1]
        lon1, lat1 = lon1[0], lon1[1]
    lon1 = math.radians(lon1)
    lat1 = math.radians(lat1)
    lon2 = math.radians(lon2)
    lat2 = math.radians(lat2)

    # haversine formula
    sdlon = math.sin((lon2 - lon1) / 2.0)
    sdlat = math.sin((lat2 - lat1) / 2.0)
    a = sdlat * sdlat + math.cos(lat1) * math.cos(lat2) * sdlon * sdlon
    c = 2 * math.asin(math.sqrt(a))
    d = r * c
    return d


def distance_bearing(lon1, lat1, bearing, d, r=6371.0):
    lon1 = math.radians(lon1)
    lat1 = math.radians(lat1)
    bearing = math.radians(bearing)
    lat2 = math.asin(math.sin(lat1) * math.cos(d / r) + math.cos(lat1) * math.sin(d / r) * math.cos(bearing))
    lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(d / r) * math.cos(lat1), math.cos(d / r) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lon2), math.degrees(lat2)


def haversine_at_const_lat(delta_deg_lon, deg_lat, r=6371.0):
    lon = math.radians(delta_deg_lon)
    lat = math.radians(deg_lat)
    clat = math.cos(lat)
    slon = math.sin(lon / 2)
    a = clat * clat * slon * slon
    c = 2 * math.asin(math.sqrt(a))
    d = r * c
    return d


def haversine_list(points, r=6371.0):
    lon1 = math.radians(points[0]['x'])
    lat1 = math.radians(points[0]['y'])

    path = 0.0
    for p in points[1:]:
        lon2 = math.radians(p['x'])
        lat2 = math.radians(p['y'])

        # haversine formula
        sdlon = math.sin((lon2 - lon1) / 2.0)
        sdlat = math.sin((lat2 - lat1) / 2.0)
        a = sdlat * sdlat + math.cos(lat1) * math.cos(lat2) * sdlon * sdlon
        c = 2 * math.asin(math.sqrt(a))
        d = r * c
        path += d
        lon1, lat1 = lon2, lat2
    return path


def km_to_string(km):
    if km < 1.0:
        s = "%d m" % (km * 1000)
    else:
        s = "%d km" % km
    return s


def km_to_rounded_string(val, sigfigs=5):
    if val < 1.0:
        val *= 1000
        unit = "m"
    else:
        unit = "km"
    format = "%%.%dg" % (sigfigs)
    val = float(format % val)
    return "%s %s" % (val, unit)


def km2_to_rounded_string(val, sigfigs=5):
    if val < 1.0:
        val *= 1000 * 1000
        unit = "m"
    else:
        unit = "km"
    unit += "\u00b2"
    format = "%%.%dg" % (sigfigs)
    val = float(format % val)
    return "%s %s" % (val, unit)


def ft_to_string(ft):
    if ft < 5000:
        s = "%d ft" % ft
    else:
        s = "%d mi" % ((ft + 280) / 5280)
    return s


def mi_to_rounded_string(val, sigfigs=5):
    if val < 1.0:
        val *= 5280
        unit = "ft"
    else:
        unit = "mi"
    format = "%%.%dg" % (sigfigs)
    val = float(format % val)
    return "%s %s" % (val, unit)


def mi2_to_rounded_string(val, sigfigs=5):
    if val < 1.0:
        val *= 5280 * 5280
        unit = "ft"
    else:
        unit = "mi"
    unit += "\u00b2"
    format = "%%.%dg" % (sigfigs)
    val = float(format % val)
    return "%s %s" % (val, unit)


def float_to_degrees_minutes_seconds(value, directions=None):
    direction = ""
    if directions:
        if value > 0:
            direction = directions[0]
        elif value < 0:
            direction = directions[1]

    degrees, minutes, seconds = to_deg_min_sec(value)

    if degrees == 0 and minutes == 0 and seconds == 0:
        direction = ""

    return (degrees, minutes, seconds, direction)


def float_to_degrees_minutes(value, directions=None):
    direction = ""
    if directions:
        if value > 0:
            direction = directions[0]
        elif value < 0:
            direction = directions[1]

    degrees, minutes = to_deg_min(value)
    return (degrees, minutes, direction)


def float_to_degrees(value, directions=None):
    direction = ""
    if directions:
        if value > 0:
            direction = directions[0]
        elif value < 0:
            direction = directions[1]

    degrees = abs(value)

    return (degrees, direction)


def check_degrees(degrees):
    if degrees < -360 or degrees > 360:
        raise ValueError("Degrees out of range")


def check_min_sec(value):
    if value < 0 or value > 60:
        raise ValueError("Value not in minutes or seconds range")


def format_lat_lon_degrees_minutes_seconds(longitude, latitude):
    lon = "%d°%d′%d″%s" % \
        float_to_degrees_minutes_seconds(longitude, directions=("E", "W"))
    lat = "%d°%d′%d″%s" % \
        float_to_degrees_minutes_seconds(latitude, directions=("N", "S"))

    return "%s, %s" % (lat, lon)


def format_lat_lon_degrees_minutes(longitude, latitude):
    lon = "%d° %0.4f′ %s" % \
        float_to_degrees_minutes(longitude, directions=("E", "W"))
    lat = "%d° %0.4f′ %s" % \
        float_to_degrees_minutes(latitude, directions=("N", "S"))

    return "%s, %s" % (lat, lon)


def format_lat_lon_degrees(longitude, latitude):
    lon = "%0.6f° %s" % \
        float_to_degrees(longitude, directions=("E", "W"))
    lat = "%0.6f° %s" % \
        float_to_degrees(latitude, directions=("N", "S"))

    return "%s, %s" % (lat, lon)


def format_coords_for_display(longitude, latitude, display_format):
    if display_format == "degrees minutes seconds":
        return format_lat_lon_degrees_minutes_seconds(longitude, latitude)
    elif display_format == "decimal degrees":
        return format_lat_lon_degrees(longitude, latitude)
    else:
        return format_lat_lon_degrees_minutes(longitude, latitude)


def format_lat_line_label(latitude):
    (degrees, minutes, direction) = \
        float_to_degrees_minutes(latitude, directions=("N", "S"))

    minutes = round(minutes)
    if minutes == 60:
        minutes = 0
        degrees += 1

    return " %d° %d' %s " % (degrees, minutes, direction)


def format_lon_line_label(longitude):
    (degrees, minutes, direction) = \
        float_to_degrees_minutes(longitude, directions=("E", "W"))

    minutes = round(minutes)
    if minutes == 60:
        minutes = 0
        degrees += 1

    return " %d° %d' %s " % (degrees, minutes, direction)


def lat_lon_from_format_string(lat_lon_string):
    lon, lat = lat_lon_string.split(",")
    dlon = parse(lon.strip())
    dlat = parse(lat.strip())
    return (dlat, dlon)


def lat_or_lon_from_format_string(lat_lon_string):
    return parse(lat_lon_string)
