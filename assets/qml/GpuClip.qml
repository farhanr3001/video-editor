import QtQuick
import QtQuick.Shapes
Rectangle {
    id: clip
    property var timeline
    property real startTime: 0
    property real duration: 1
    property bool selected: false
    property bool audio: false
    property bool caption: false
    property bool textItem: false
    property bool hovered: false
    property bool ghost: false
    property string label: ""
    property string thumbnail: ""
    property real thumbnailAspect: 1.777778
    property string waveform: ""
    property real waveResolution: 0.001
    property real waveCount: 0
    property real sourceIn: 0
    property real sourceSpeed: 1
    property real gain: 1
    property real fadeIn: 0
    property real fadeOut: 0
    property bool retime: false
    property bool linked: false
    property bool hasEffects: false
    property string effectLabel: ""
    property real sectionTop: 0
    property real sectionBottom: 1000
    property real laneY: 0
    property real laneHeight: 60
    property real fadeWidthIn: Math.min(width,fadeIn*timeline.pixelsPerSecond)
    property real fadeWidthOut: Math.min(width,fadeOut*timeline.pixelsPerSecond)
    x: visible ? startTime*timeline.pixelsPerSecond-timeline.scrollOffset : 0
    y: Math.max(laneY,sectionTop)
    width: visible ? Math.max(5,duration*timeline.pixelsPerSecond) : 1
    height: Math.max(0,Math.min(laneY+laneHeight,sectionBottom)-y)
    color: audio ? "#326951" : "#3c6c90"
    radius: 3
    border.color: selected ? "#f05a50" : "#08090b"
    border.width: selected ? 2 : 1
    clip: true
    Image { id: thumb; source: clip.thumbnail; visible: false; asynchronous: true; retainWhileLoading: true; sourceSize: Qt.size(320,180) }
    ShaderEffect {
        x: 2; y: Math.max(2,clip.laneY-clip.y+2); width: parent.width-4; height: Math.max(0,Math.min(clip.height-y-2,clip.laneHeight-25))
        visible: !clip.audio && clip.thumbnail!=="" && clip.width>=28 && clip.laneHeight>=52
        property var source: thumb
        property real repeatCount: width/Math.max(1,height*clip.thumbnailAspect)
        fragmentShader: "../shaders/thumbnail.frag.qsb"
    }
    Image { id: peaks; source: clip.waveform; visible: false; smooth: false; asynchronous: false; retainWhileLoading: true }
    ShaderEffect {
        x: 3; y: clip.laneY-clip.y+6; width: Math.max(1,parent.width-6); height: Math.max(4,clip.laneHeight-25)
        visible: clip.audio && clip.waveform!=="" && clip.waveCount>0
        property var source: peaks
        property vector4d mapping: Qt.vector4d(clip.sourceIn,clip.sourceSpeed,clip.waveResolution,clip.waveCount)
        property vector4d timing: Qt.vector4d(clip.duration,clip.fadeIn,clip.fadeOut,clip.gain)
        property vector2d textureSize: Qt.vector2d(peaks.sourceSize.width,peaks.sourceSize.height)
        property real pixelsPerSecond: clip.timeline.pixelsPerSecond
        property real clipWidth: clip.width
        fragmentShader: "../shaders/waveform.frag.qsb"
    }
    Text {
        property bool wrapped: clip.caption || clip.textItem
        x: wrapped ? 4 : 6; y: clip.laneY-clip.y+(wrapped ? (clip.textItem?14:4) : clip.laneHeight-21)
        width: Math.max(0,parent.width-(wrapped?8:12)-(clip.linked?18:0)); height: wrapped ? clip.laneHeight-(clip.textItem?17:7) : 20
        text: clip.label; color: wrapped ? "#151515" : "white"; font.family: "Segoe UI"; font.pixelSize: wrapped ? 11 : 12
        font.weight: wrapped ? Font.DemiBold : Font.Normal
        wrapMode: wrapped ? Text.Wrap : Text.NoWrap
        elide: wrapped ? Text.ElideNone : Text.ElideRight
        verticalAlignment: wrapped ? Text.AlignTop : Text.AlignVCenter
        maximumLineCount: wrapped ? Math.max(1,Math.floor(height/13)) : 1
        clip: true; visible: parent.width >= (wrapped?14:44)
    }
    Shape {
        visible: clip.fadeIn>0 && (clip.audio || clip.selected || clip.hovered)
        ShapePath {
            strokeColor: "#faf0c2"; strokeWidth: 1; fillColor: "#7d000000"
            startX: 0; startY: clip.height
            PathCubic { x: clip.fadeWidthIn; y: 3; control1X: clip.fadeWidthIn*.3; control1Y: clip.height-(clip.height-3)*.35; control2X: clip.fadeWidthIn*.7; control2Y: 3+(clip.height-3)*.25 }
            PathLine { x: 0; y: 3 }
            PathLine { x: 0; y: clip.height }
        }
    }
    Shape {
        visible: clip.fadeOut>0 && (clip.audio || clip.selected || clip.hovered)
        ShapePath {
            strokeColor: "#faf0c2"; strokeWidth: 1; fillColor: "#7d000000"
            startX: clip.width-clip.fadeWidthOut; startY: 3
            PathCubic { x: clip.width; y: clip.height; control1X: clip.width-clip.fadeWidthOut*.7; control1Y: 3+(clip.height-3)*.25; control2X: clip.width-clip.fadeWidthOut*.3; control2Y: clip.height-(clip.height-3)*.35 }
            PathLine { x: clip.width; y: 3 }
            PathLine { x: clip.width-clip.fadeWidthOut; y: 3 }
        }
    }
    Repeater {
        model: clip.width>=34 && (clip.audio || clip.selected || clip.hovered) ? 2 : 0
        Shape {
            required property int index
            x: index===0 ? Math.max(5,clip.fadeWidthIn) : clip.width-Math.max(5,clip.fadeWidthOut)
            ShapePath {
                strokeColor: "#151515"; strokeWidth: 1; fillColor: "white"
                startX: -4; startY: 2
                PathLine { x: 4; y: 2 }
                PathLine { x: 4; y: 8 }
                PathCubic { x: -4; y: 8; control1X: 4; control1Y: 13; control2X: -4; control2Y: 13 }
                PathLine { x: -4; y: 2 }
            }
        }
    }
    Rectangle { visible: clip.retime; width: parent.width; height: 17; color: "#244157"; Text { x: 5; text: "×  Speed Change"; color: "white"; font.pixelSize: 11 } }
    Rectangle { visible: clip.retime; width: parent.width; height: 21; y: parent.height-21; color: "#244157"; Text { anchors.centerIn: parent; text: (clip.sourceSpeed*100).toFixed(0)+"%  ▾"; color: "white"; font.pixelSize: 11 } }
    Text { visible: clip.linked && clip.width>=110; x: parent.width-20; y: parent.height-20; text: "↔"; color: "#e9eef5"; font.pixelSize: 14 }
    Rectangle {
        visible: clip.hasEffects && clip.width>70; x: Math.max(5,-clip.x+5); y: 12; width: 22; height: 15; color: "#202833"
        Text { anchors.centerIn: parent; text: "fx"; color: "#afc6e1"; font.pixelSize: 10; font.bold: true }
    }
    Rectangle { visible: clip.ghost; anchors.fill: parent; color: "#60adb4c0"; border.color: "#e0e5ed"; border.width: 1; radius: 3 }
    Rectangle { visible: clip.effectLabel!==""; anchors.fill: parent; color: "#73acb5c2"; border.color: "#dfe8f5"; border.width: 2; radius: 3; Text { anchors.centerIn: parent; text: clip.effectLabel; color: "white"; font.pixelSize: 12 } }
    Rectangle { anchors.fill: parent; color: "transparent"; radius: 3; border.color: clip.selected?"#f05a50":"#08090b"; border.width: clip.selected?2:1 }
}
