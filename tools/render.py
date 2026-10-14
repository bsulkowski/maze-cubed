"""Simple z-buffer renderer (numpy) for previewing an STL mesh."""
import sys
import numpy as np
import trimesh
from PIL import Image


def look(el, az):
    el, az = np.radians(el), np.radians(az)
    d = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])  # direction towards the camera
    right = np.cross([0, 0, 1], d); right /= np.linalg.norm(right)
    up = np.cross(d, right)
    return np.stack([right, up, d])


def render(mesh, el, az, size=600, center=None, span=None, colors=None):
    R = look(el, az)
    v = mesh.vertices - (mesh.bounds.mean(0) if center is None else center)
    p = v @ R.T
    span = span or np.abs(p[:, :2]).max() * 2.2
    s = size / span
    xy = p[:, :2] * s + size / 2
    xy[:, 1] = size - xy[:, 1]
    z = p[:, 2]
    light = np.array([0.35, 0.55, 0.75]); light /= np.linalg.norm(light)
    n = mesh.face_normals @ R.T
    shade = 0.25 + 0.75 * np.clip(n @ light, 0, 1)
    img = np.ones((size, size, 3))
    zb = np.full((size, size), -np.inf)
    base = np.array([0.22, 0.5, 0.82])
    cols = np.tile(base, (len(mesh.faces), 1)) if colors is None else np.asarray(colors)
    for f, sh, col in zip(mesh.faces, shade, cols):
        a, b, c = xy[f]
        if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) >= 0:
            continue  # back face
        x0, x1 = int(max(min(a[0], b[0], c[0]), 0)), int(min(max(a[0], b[0], c[0]) + 1, size))
        y0, y1 = int(max(min(a[1], b[1], c[1]), 0)), int(min(max(a[1], b[1], c[1]) + 1, size))
        if x0 >= x1 or y0 >= y1:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        w0 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / den
        w1 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / den
        w2 = 1 - w0 - w1
        m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        zz = w0 * z[f[0]] + w1 * z[f[1]] + w2 * z[f[2]]
        sub = zb[y0:y1, x0:x1]
        m &= zz > sub
        sub[m] = zz[m]
        img[y0:y1, x0:x1][m] = col * sh
    return (img * 255).astype(np.uint8)


if __name__ == "__main__":
    mesh = trimesh.load(sys.argv[1])
    out = sys.argv[2]
    a = render(mesh, 25, -55)
    b = render(mesh, 55, 25)
    corner = mesh.bounds[1] - 3.0
    c = render(mesh, 30, 30, center=corner, span=12)  # close-up of the top corner
    Image.fromarray(np.hstack([a, b, c])).save(out)
