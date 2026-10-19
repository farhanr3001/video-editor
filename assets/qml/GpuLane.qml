import QtQuick
Rectangle {
    property real laneY: 0
    property real laneHeight: 60
    property real sectionTop: 0
    property real sectionBottom: 1000
    y: Math.max(laneY,sectionTop)
    height: Math.max(0,Math.min(laneY+laneHeight,sectionBottom)-y)
    width: parent.width
    color: "#202126"
    border.color: "#111215"
    border.width: 1
    z: -1000
}
