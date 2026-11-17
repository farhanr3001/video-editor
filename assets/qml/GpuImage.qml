import QtQuick
Image {
    property alias texture: image
    // Preview media opts in. Timeline chrome/selection overlays keep their
    // existing sampling and allocation behavior.
    property bool minification: false
    mipmap: minification
    id: image
    objectName: "texture"
    visible: false
    cache: false
    retainWhileLoading: true
    fillMode: Image.Stretch
    // Invoked queued from Python (Surface.publish) so image loads start from
    // Qt's event loop instead of inside a GIL-holding setProperty call.
    function publishProperty(name, value) { image[name] = value }
}
