import QtQuick

Rectangle {
    id: root
    color: background
    property color background: "#191a1d"
    property real canvasX: 0
    property real canvasY: 0
    property real canvasWidth: 100
    property real canvasHeight: 100
    property real timelineTime: 0
    property alias canvas: canvas
    property alias sources: sourceHost
    Item { id: sourceHost; objectName: "sources" }
    Rectangle {
        id: canvas
        objectName: "canvas"
        x: root.canvasX; y: root.canvasY
        width: root.canvasWidth; height: root.canvasHeight
        color: "black"
        clip: true
    }
}
