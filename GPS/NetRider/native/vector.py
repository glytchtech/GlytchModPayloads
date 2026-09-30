"""Small bounded Mapbox Vector Tile reader for OpenMapTiles road geometry."""
import math


def varint(data, position):
    value = shift = 0
    while position < len(data) and shift < 70:
        byte = data[position]; position += 1
        value |= (byte & 127) << shift
        if byte < 128: return value, position
        shift += 7
    raise ValueError('Invalid protobuf varint')


def fields(data):
    position = 0
    while position < len(data):
        key, position = varint(data, position)
        number, wire = key >> 3, key & 7
        if wire == 0: value, position = varint(data, position)
        elif wire in (1,2,5):
            if wire == 2: size, position = varint(data, position)
            else: size = 8 if wire == 1 else 4
            if position+size > len(data): raise ValueError('Truncated protobuf field')
            value = data[position:position+size]; position += size
        else: raise ValueError('Unsupported protobuf wire type')
        yield number, value


def packed(data):
    out, position = [], 0
    while position < len(data):
        value, position = varint(data, position)
        out.append(value)
    return out


def geometry(commands, extent, z, tile_x, tile_y):
    x = y = position = 0
    line = []
    paths = []
    while position < len(commands):
        command = commands[position]; position += 1
        kind, count = command & 7, command >> 3
        if kind == 7: continue
        if kind not in (1,2) or count > 65536: raise ValueError('Invalid vector geometry')
        for _ in range(count):
            if position+2 > len(commands): raise ValueError('Truncated vector geometry')
            a, b = commands[position:position+2]; position += 2
            x += (a >> 1) ^ -(a & 1)
            y += (b >> 1) ^ -(b & 1)
            if kind == 1 and line:
                paths.append(line); line = []
            lon = (tile_x+x/extent)/(2**z)*360-180
            merc = math.pi*(1-2*(tile_y+y/extent)/(2**z))
            if abs(merc) > 10: raise ValueError('Vector point outside Mercator extent')
            lat = math.degrees(math.atan(math.sinh(merc)))
            line.append((lat,lon))
    if line: paths.append(line)
    return paths


def roads_from_tile(raw, z, x, y):
    roads = []
    budget = 14000
    for number, layer in fields(raw):
        if number != 3: continue
        values, keys, features = [], [], []
        name, extent = '', 4096
        for field, value in fields(layer):
            if field == 1: name = value.decode('utf-8','replace')
            elif field == 2: features.append(value)
            elif field == 3: keys.append(value.decode('utf-8','replace'))
            elif field == 4:
                entries = dict(fields(value))
                values.append(entries.get(1, b'').decode('utf-8','replace'))
            elif field == 5: extent = value
        if name not in ('transportation','transportation_name') or extent <= 0: continue
        for feature in features:
            props = dict(fields(feature))
            if props.get(3) != 2: continue
            tags = packed(props.get(2,b''))
            attrs = {}
            for i in range(0,len(tags)-1,2):
                if tags[i] < len(keys) and tags[i+1] < len(values):
                    attrs[keys[tags[i]]] = values[tags[i+1]]
            for path in geometry(packed(props.get(4,b'')), extent,z,x,y):
                if len(path) < 2: continue
                path = path[:budget]
                roads.append({'points':path, 'name':attrs.get('name:latin') or attrs.get('name',''),
                              'kind':attrs.get('class',''),
                              'bounds': [min(p[0] for p in path), min(p[1] for p in path),
                                         max(p[0] for p in path), max(p[1] for p in path)]})
                budget -= len(path)
                if budget <= 0: return roads
    return roads
