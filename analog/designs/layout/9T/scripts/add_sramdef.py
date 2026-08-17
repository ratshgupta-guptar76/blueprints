import pya

layout = pya.Layout()
layout.read(input_gds)

top = layout.top_cell()
top.shapes(layout.layer(108, 5)).insert(top.bbox())

layout.write(output_gds)
print(f"SRAMDEF added on 108/5 covering {top.bbox()} -> {output_gds}")
