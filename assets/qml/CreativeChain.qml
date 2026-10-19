import QtQuick

Item {
    id: chain
    property var inputTexture: null
    property var effects: []
    property size rasterSize
    property int generation: 0
    property var outputTexture: {
        let revision = generation
        let last = passes.count ? passes.itemAt(passes.count-1) : null
        return last ? last.outputTexture : inputTexture
    }
    Repeater {
        id: passes
        model: chain.effects.length
        onItemAdded: chain.generation++
        onItemRemoved: chain.generation++
        delegate: Item {
            id: pass
            required property int index
            width: chain.width; height: chain.height
            property var settings: chain.effects[index] || ({p1:[0,0,0,0],p2:[0,0,0,0],colorA:[1,1,1,1],colorB:[1,1,1,1],mode:6,time:0})
            property alias outputTexture: rendered
            ShaderEffect {
                id: shader
                anchors.fill: parent
                property var source: {
                    let revision = chain.generation
                    let previous = pass.index>0 ? passes.itemAt(pass.index-1) : null
                    return previous ? previous.outputTexture : chain.inputTexture
                }
                property vector4d p1: Qt.vector4d(pass.settings.p1[0],pass.settings.p1[1],pass.settings.p1[2],pass.settings.p1[3])
                property vector4d p2: Qt.vector4d(pass.settings.p2[0],pass.settings.p2[1],pass.settings.p2[2],Math.max(1,chain.rasterSize.width)/Math.max(1,chain.rasterSize.height))
                property vector4d colorA: Qt.vector4d(pass.settings.colorA[0],pass.settings.colorA[1],pass.settings.colorA[2],1)
                property vector4d colorB: Qt.vector4d(pass.settings.colorB[0],pass.settings.colorB[1],pass.settings.colorB[2],1)
                property real mode: pass.settings.mode
                property real effectTime: pass.settings.time
                fragmentShader: pass.settings.shader || "../shaders/creative.frag.qsb"
            }
            ShaderEffectSource {
                id: rendered
                sourceItem: shader
                textureSize: chain.rasterSize
                hideSource: true; visible: false
            }
        }
    }
}
