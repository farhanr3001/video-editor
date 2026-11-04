import QtQuick

// Motion Composition editor canvas. The composition itself is drawn by GpuMotion.qml (created into "canvas") on the GPU,
// exactly like the live preview and export; selection handles, guides and the safe area arrive as a small overlay image.
Rectangle {
    id: root
    color: "#191a1e"
    Rectangle { objectName: "board"; color: "#111317" }
    Item { objectName: "canvas"; anchors.fill: parent }
    Image { objectName: "overlay"; anchors.fill: parent; z: 100000; cache: false; asynchronous: false; smooth: false }
}
