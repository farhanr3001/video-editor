import QtQuick

Item {
    id: layer
    property var texture: null
    property var beforeEffects: []
    property var afterEffects: []
    property matrix4x4 placement
    property vector4d cropRect: Qt.vector4d(0, 0, 1, 1)
    property vector4d grade: Qt.vector4d(0, 1, 1, 1)
    property real alpha: 1
    property bool ellipse: false
    property real blurX: 0
    property real blurY: 0
    property real blurMix: 1
    property real borderMode: 1
    property real rasterScale: 1
    property real sharpen: 0
    property vector2d pixelStep: Qt.vector2d(0,0)
    property size processingSize: Qt.size(1024,1024)
    property size rasterSize: Qt.size(Math.max(2,Math.ceil(processingSize.width*rasterScale)), Math.max(2,Math.ceil(processingSize.height*rasterScale)))
    transform: Matrix4x4 { matrix: layer.placement }
    ShaderEffect {
        id: graded
        anchors.fill: parent
        property var source: layer.texture
        property vector4d cropRect: layer.cropRect
        property vector4d grade: layer.grade
        property real alpha: 1
        property real ellipse: 0
        property real sharpen: layer.sharpen
        property vector2d pixelStep: layer.pixelStep
        fragmentShader: "../shaders/layer.frag.qsb"
    }
    ShaderEffectSource {
        id: gradedTexture
        objectName: "gradedTexture"
        sourceItem: graded
        hideSource: true; visible: false
        textureSize: layer.rasterSize
        smooth: true; mipmap: true
    }
    CreativeChain {
        id: beforeChain
        anchors.fill: parent
        inputTexture: gradedTexture
        effects: layer.beforeEffects
        rasterSize: layer.rasterSize
        effectAspect: layer.width/Math.max(0.001,layer.height)
    }
    ShaderEffect {
        id: horizontal
        anchors.fill: parent
        property var source: beforeChain.outputTexture
        property var original: beforeChain.outputTexture
        property vector2d stepSize: Qt.vector2d(layer.blurX / Math.max(1, layer.width), 0)
        property real mixAmount: 1
        property real borderMode: layer.borderMode
        property real alpha: 1
        property real ellipse: 0
        fragmentShader: "../shaders/blur.frag.qsb"
    }
    ShaderEffectSource {
        id: horizontalTexture
        objectName: "horizontalTexture"
        sourceItem: horizontal
        hideSource: true; visible: false
        textureSize: layer.rasterSize
        smooth: true; mipmap: true
    }
    ShaderEffect {
        id: vertical
        anchors.fill: parent
        property var source: horizontalTexture
        property var original: beforeChain.outputTexture
        property vector2d stepSize: Qt.vector2d(0, layer.blurY / Math.max(1, layer.height))
        property real mixAmount: layer.blurMix
        property real borderMode: layer.borderMode
        property real alpha: layer.alpha
        property real ellipse: layer.ellipse ? 1 : 0
        fragmentShader: "../shaders/blur.frag.qsb"
    }
    ShaderEffectSource {
        id: verticalTexture
        objectName: "verticalTexture"
        sourceItem: vertical
        hideSource: true; visible: false
        textureSize: layer.rasterSize
        smooth: true; mipmap: true
    }
    CreativeChain {
        id: afterChain
        anchors.fill: parent
        inputTexture: verticalTexture
        effects: layer.afterEffects
        rasterSize: layer.rasterSize
        effectAspect: layer.width/Math.max(0.001,layer.height)
    }
    ShaderEffect {
        anchors.fill: parent
        property var source: afterChain.outputTexture
        fragmentShader: "../shaders/creative_copy.frag.qsb"
    }

}
