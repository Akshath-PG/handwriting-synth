import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src" if "legacy" not in __file__ else ".."))
import math
from hw_render import *

page = Page(seed=5)
pen = Pen(page, cap=50, jitter=1.0, seed=11)
S = 50 / CAP

LEFT, RIGHT = 330, 2380
# pencil margin line like the notes
page.pencil_line(285, 120, 285, 3400, width=2)
page.pencil_line(285, 400, 2430, 400, width=2)

# header
pen.run('Advanced Algorithm And Design', LEFT + 20, 330, S * 1.2)
pen.run('AKSHATH P.G', 1900, 215, S * 0.85)
pen.run('CB.SC.P2AIE26004', 1800, 285, S * 0.85)

# title
title = 'Vanilla GCN'
tw = pen.width(title, S * 1.5)
tx = (LEFT + RIGHT) / 2 - tw / 2
pen.run(title, tx, 560, S * 1.5)
page.line(tx - 10, 600, tx + tw * 0.46, 604, width=4)
page.line(tx + tw * 0.52, 604, tx + tw + 10, 600, width=4)

y = 780
pen.run('1. Definition', LEFT, y, S * 1.25)
w = pen.width('1. Definition', S * 1.25)
page.line(LEFT, y + 22, LEFT + w, y + 20, width=4)
y += 130

body_cap = S
line_h = 104


def para(text, y, indent=0, first_prefix=None, scale=1.0):
    lines = pen.wrap(text, RIGHT - LEFT - indent - 20, S * scale)
    for i, ln in enumerate(lines):
        drift = 4 * math.sin(y / 260.0)
        x = LEFT + indent + pen.r.gauss(0, 3)
        pen.run(ln, x, y + drift + pen.r.gauss(0, 2), S * scale)
        y += line_h
    return y


y = para('A vanilla GCN is a neural network that takes a graph G(V,E) with n nodes, an adjacency matrix A (n × n) '
         'and a node-feature matrix X (n × F), and produces a new feature matrix for every node by repeating one '
         'propagation rule layer after layer.', y)
y += 20
y = para('The rule, from Kipf and Welling (2017), for layer l is:', y)
y += 40
f = 'H^{(l+1)} = σ( \\h{D}^{-1/2} Â \\h{D}^{-1/2} H^{(l)} W^{(l)} ) , H^{(0)} = X'
fw = pen.width(f, S)
pen.run(f, (LEFT + RIGHT) / 2 - fw / 2, y, S)
y += 150
y = para('where:', y)
bul = [
    'Â = A + I is the adjacency matrix with a self-loop added to every node.',
    '\\h{D} is the diagonal degree matrix of Â, with \\h{D}_{ii} = Σ_{j} Â_{ij}.',
    'H^{(l)} (n × F_{l}) holds the node features at layer l; W^{(l)} (F_{l} × F_{l+1}) is the learnable weight matrix, '
    'shared by all nodes.',
    'σ is a nonlinearity, usually ReLU; the last layer uses softmax for node classification.',
]
for b in bul:
    pen.run('-', LEFT + 30, y, S)
    y = para(b, y, indent=100)
    y += 6
y += 20
y = para("In short: each node collects its neighbours' (and its own) features, scales them by the degrees, mixes "
         "channels with W, and applies σ.", y)

page.save(D + 'pilot_page1.png')
print('done', y)
