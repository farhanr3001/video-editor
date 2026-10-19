import QtQuick
Item {
    id: pair
    property real progress: 0
    property vector4d p1: Qt.vector4d(1,8,0,0)
    property vector4d p2: Qt.vector4d(.5,.5,0,1)
    property url shader: "../shaders/transition_1.frag.qsb"
    property real rasterScale: Math.min(1,2048/Math.max(1,width,height))
    property size rasterSize: Qt.size(Math.max(2,Math.ceil(width*rasterScale)),Math.max(2,Math.ceil(height*rasterScale)))
    Item { id: outgoing; objectName: "outgoing"; anchors.fill: parent }
    Item { id: incoming; objectName: "incoming"; anchors.fill: parent }
    ShaderEffectSource { id: a; sourceItem: outgoing; hideSource: true; visible: false; textureSize: pair.rasterSize }
    ShaderEffectSource { id: b; sourceItem: incoming; hideSource: true; visible: false; textureSize: pair.rasterSize }
    ShaderEffect {
        anchors.fill: parent
        property var sourceA: a
        property var sourceB: b
        property real effectTime: pair.progress
        property vector4d p1: pair.p1
        property vector4d p2: pair.p2
        fragmentShader: pair.shader
    }
}
