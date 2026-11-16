"""Makes an exported ONNX file readable by older OpenCV versions, as on a Raspberry with Debian Bookworm (OpenCV 4.6):
newer PyTorch versions write "Identity" nodes (a value passed on unchanged) that OpenCV 4.6 refuses ("ERROR during
processing node ... [Identity]"). They are taken out; what the network computes does not change.

    python ml/onnx_tidy.py model.onnx [more.onnx ...]
"""
import sys


def without_identities(path):
    """Takes the Identity nodes out of the ONNX file at `path` (rewritten in place). -> how many were taken out."""
    import onnx
    from onnx import numpy_helper

    model = onnx.load(path)
    graph = model.graph
    initializers = {init.name: init for init in graph.initializer}
    outputs = {o.name for o in graph.output}
    removed = 0
    for node in [n for n in graph.node if n.op_type == "Identity"]:
        source, target = node.input[0], node.output[0]
        graph.node.remove(node)
        removed += 1
        if source in initializers:   # a constant passed on: the same constant under the new name
            copy = numpy_helper.from_array(numpy_helper.to_array(initializers[source]), target)
            graph.initializer.append(copy)
            initializers[target] = copy
            continue
        if target in outputs:   # the network's output: the node that made the value now writes it under that name
            for other in graph.node:
                for i, name in enumerate(other.output):
                    if name == source:
                        other.output[i] = target
                for i, name in enumerate(other.input):
                    if name == source:
                        other.input[i] = target
            continue
        for other in graph.node:   # everywhere else: read the value it came from
            for i, name in enumerate(other.input):
                if name == target:
                    other.input[i] = source
    if removed:
        onnx.checker.check_model(model)
        onnx.save(model, path)
    return removed


if __name__ == "__main__":
    for file in sys.argv[1:]:
        print("%s: %d Identity node(s) taken out" % (file, without_identities(file)))
