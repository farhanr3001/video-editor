import QtQuick
import QtQuick.Shapes

Rectangle {
    id: monitor
    color: "#101114"
    property real aspect: 1.7778
    property bool still: false
    property var region: []
    property var markers: []
    property var cropGuide: [0,0,1,1]
    property bool showMarkers: true
    property bool drawTarget: true
    property bool showGizmo: false
    property var selection: ({cx:0,cy:0,left:0,top:0,w:0,h:0,rotation:0})
    GpuSource { id: video; objectName: "trackingVideo" }
    GpuImage { id: photo; objectName: "trackingPhoto"; minification: true; asynchronous: true }
    Item {
        id: frame
        clip: true
        anchors.centerIn: parent
        width: Math.min(parent.width, parent.height * monitor.aspect)
        height: width / monitor.aspect
        GpuLayer { anchors.fill: parent; texture: monitor.still ? photo : video.texture }
        Repeater {
            model: monitor.showMarkers ? monitor.markers : []
            delegate: Item {
                required property var modelData
                x: modelData.x * frame.width
                y: modelData.y * frame.height
                width: modelData.w * frame.width
                height: modelData.h * frame.height
                rotation: modelData.rotation
                opacity: modelData.opacity
                GpuLayer {
                    anchors.fill: parent
                    visible: modelData.mode === "Blur"
                    texture: monitor.still ? photo : video.texture
                    cropRect: Qt.vector4d(modelData.x, modelData.y, modelData.w, modelData.h)
                    blurX: modelData.blur
                    blurY: modelData.blur
                    processingSize: Qt.size(Math.min(2048,Math.max(2,width)),Math.min(2048,Math.max(2,height)))
                }
                GpuLayer {
                    id: pixelBase
                    anchors.fill: parent
                    visible: modelData.mode === "Pixelate"
                    texture: monitor.still ? photo : video.texture
                    cropRect: Qt.vector4d(modelData.x, modelData.y, modelData.w, modelData.h)
                }
                ShaderEffectSource {
                    visible: modelData.mode === "Pixelate"
                    anchors.fill: parent
                    sourceItem: visible ? pixelBase : null
                    hideSource: true
                    textureSize: Qt.size(Math.min(2048,Math.max(1,Math.round(width/Math.max(2,modelData.pixel_size)))), Math.min(2048,Math.max(1,Math.round(height/Math.max(2,modelData.pixel_size)))))
                    smooth: false
                }
                Rectangle {
                    anchors.fill: parent
                    visible: ["Rectangle", "Censor Bar"].indexOf(modelData.mode) >= 0
                    radius: modelData.mode === "Circle" ? Math.max(width, height) : modelData.radius
                    color: modelData.fill || modelData.mode === "Censor Bar" ? modelData.color : "transparent"
                    border.color: modelData.color
                    border.width: modelData.stroke
                }
                Shape {
                    anchors.fill: parent
                    visible: modelData.mode === "Circle"
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        fillColor: modelData.fill ? modelData.color : "transparent"
                        strokeColor: modelData.color
                        strokeWidth: modelData.stroke
                        PathSvg { path: "M 0,"+(height/2)+" A "+(width/2)+","+(height/2)+" 0 1 0 "+width+","+(height/2)+" A "+(width/2)+","+(height/2)+" 0 1 0 0,"+(height/2) }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: modelData.mode === "Label"
                    text: modelData.label
                    color: modelData.label_color
                    font.family: modelData.font
                    font.pixelSize: modelData.font_size
                    font.bold: true
                    Rectangle { anchors.fill: parent; anchors.margins: -modelData.label_padding; radius: modelData.radius; color: modelData.label_background; z: -1 }
                }
                Image { anchors.fill: parent; fillMode: Image.PreserveAspectFit; visible: modelData.mode === "Image"; source: modelData.image }
                Item {
                    visible: modelData.mode === "Arrow"
                    anchors.centerIn: parent
                    Rectangle { x: -modelData.arrow_length; y: -modelData.stroke/2; width: modelData.arrow_length-modelData.arrow_head*0.65; height: modelData.stroke; radius: modelData.stroke/2; color: modelData.color }
                    Shape {
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath {
                            fillColor: modelData.color
                            strokeWidth: 0
                            startX: 0; startY: 0
                            PathLine { x: -modelData.arrow_head; y: -modelData.arrow_head*0.55 }
                            PathLine { x: -modelData.arrow_head; y: modelData.arrow_head*0.55 }
                            PathLine { x: 0; y: 0 }
                        }
                    }
                }
            }
        }
        Rectangle {
            x: monitor.cropGuide[0]*frame.width
            y: monitor.cropGuide[1]*frame.height
            width: monitor.cropGuide[2]*frame.width
            height: monitor.cropGuide[3]*frame.height
            color: "transparent"
            border.color: "#8bc9ff"
            border.width: 1
        }
        Rectangle {
            visible: monitor.drawTarget && monitor.region.length === 4
            x: visible ? monitor.region[0] * frame.width : 0
            y: visible ? monitor.region[1] * frame.height : 0
            width: visible ? monitor.region[2] * frame.width : 0
            height: visible ? monitor.region[3] * frame.height : 0
            color: "transparent"
            border.color: "#46e0ad"
            border.width: 2
        }
    }
    Item {
        visible: monitor.showGizmo
        x: frame.x + monitor.selection.cx * frame.width
        y: frame.y + monitor.selection.cy * frame.height
        rotation: monitor.selection.rotation
        property real gizmoLeft: monitor.selection.left * frame.width
        property real gizmoTop: monitor.selection.top * frame.height
        property real boxWidth: monitor.selection.w * frame.width
        property real boxHeight: monitor.selection.h * frame.height
        Rectangle { x: parent.gizmoLeft; y: parent.gizmoTop; width: parent.boxWidth; height: parent.boxHeight; color: "transparent"; border.color: "#7dbbff"; border.width: 1 }
        Rectangle { x: parent.gizmoLeft + parent.boxWidth/2; y: parent.gizmoTop - 24; width: 1; height: 24; color: "#7dbbff" }
        Rectangle { x: parent.gizmoLeft + parent.boxWidth/2 - 4; y: parent.gizmoTop - 28; width: 8; height: 8; radius: 4; color: "white"; border.color: "#7dbbff"; border.width: 1 }
        Repeater {
            model: [[0,0],[0.5,0],[1,0],[1,0.5],[1,1],[0.5,1],[0,1],[0,0.5]]
            delegate: Rectangle {
                required property var modelData
                x: parent.gizmoLeft + parent.boxWidth * modelData[0] - 4
                y: parent.gizmoTop + parent.boxHeight * modelData[1] - 4
                width: 8; height: 8; color: "white"; border.color: "#7dbbff"; border.width: 1
            }
        }
    }
}
