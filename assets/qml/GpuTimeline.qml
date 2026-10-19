import QtQuick
import QtQuick.Shapes
Rectangle {
    id: root
    color: "#191a1e"
    property real pixelsPerSecond: 20
    property real scrollOffset: 0
    property real playhead: 0
    property real guide: -1
    property real bodyX: 186
    property real bodyY: 28
    property real fps: 60
    property string clockText: "00:00:00:00"
    property string headerSource: ""
    property color rulerColor: "#26272c"
    property color textColor: "#b7bac1"
    property rect marquee: Qt.rect(0,0,0,0)
    property real major: { const steps=[1,5,10,15,30,60,120,300,600]; for(let i=0;i<steps.length;i++)if(steps[i]*pixelsPerSecond>=75)return steps[i];return 600; }
    property int divisions: Math.max(2,Math.min(20,Math.round(major*pixelsPerSecond/8)))
    property real minor: major/divisions
    property int first: Math.max(0,Math.floor(scrollOffset/(pixelsPerSecond*minor))-1)
    property int rulerTickCount: 256
    property bool nativeRuler: false
    property bool originalChrome: false
    clip: true
    Item {
        id: body
        objectName: "body"
        x: root.bodyX; y: root.bodyY
        width: Math.max(0,parent.width-x); height: Math.max(0,parent.height-y)
        clip: true
        Rectangle { visible: !root.originalChrome; x: root.playhead * root.pixelsPerSecond-root.scrollOffset; width: 1; height: parent.height; color: "#ed5060"; z: 100000 }
        Rectangle { x: root.guide * root.pixelsPerSecond-root.scrollOffset; visible: root.guide>=0; width: 1; height: parent.height; color: "#f3d45f"; z: 99999 }
    }
    // The live box is geometry, not a new full-viewport image per mouse move.
    // It covers section dividers exactly as the original painter overlay did.
    Item {
        x: root.bodyX; y: root.bodyY-1
        width: Math.max(0,parent.width-x); height: Math.max(0,parent.height-y)
        clip: true; z: 1000009
        Shape {
            x: root.marquee.x-parent.x; y: root.marquee.y-parent.y
            width: root.marquee.width; height: root.marquee.height
            visible: width>0 && height>0
            ShapePath {
                strokeColor: "#acbfd6"; strokeWidth: 1
                strokeStyle: ShapePath.DashLine; dashPattern: [4,2]
                fillColor: "#2388add8"
                startX: 0; startY: 0
                PathLine { x: root.marquee.width; y: 0 }
                PathLine { x: root.marquee.width; y: root.marquee.height }
                PathLine { x: 0; y: root.marquee.height }
                PathLine { x: 0; y: 0 }
            }
        }
    }
    Image { source: root.headerSource; x: 0; y: 0; width: root.bodyX; height: root.height; fillMode: Image.Stretch; cache: false; retainWhileLoading: true; z: 1 }
    Rectangle { visible: !root.nativeRuler; x: root.bodyX; y: 0; width: parent.width-x; height: root.bodyY; color: root.rulerColor; clip: true; z: 2
        Repeater {
            model: root.nativeRuler ? 0 : root.rulerTickCount
            Item {
                required property int index
                visible: index < Math.ceil(parent.width/(root.pixelsPerSecond*root.minor))+3
                property int unit: root.first+index
                property real moment: unit*root.minor
                property bool majorTick: unit%root.divisions===0
                x: Math.round(moment*root.pixelsPerSecond)-root.scrollOffset
                Rectangle { y: root.bodyY-(parent.majorTick?12:4); width: 1; height: parent.majorTick?12:4; color: root.textColor }
                Text { visible: parent.majorTick; x: 4; y: 1; text: { let seconds=Math.round(parent.moment);return Math.floor(seconds/60).toString().padStart(2,'0')+':'+(seconds%60).toString().padStart(2,'0'); } color: root.textColor; font.family: "Segoe UI"; font.pixelSize: 11 }
            }
        }
    }
    Text { visible: !root.nativeRuler; x: 16; y: 1; width: root.bodyX-24; height: root.bodyY-1; text: root.clockText; color: root.textColor; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true; verticalAlignment: Text.AlignVCenter; z: 3 }
    Rectangle { x: root.bodyX+root.playhead*root.pixelsPerSecond-root.scrollOffset-4; y: root.bodyY-7; width: 8; height: 8; rotation: 45; color: "#ed5060"; visible: !root.originalChrome && x>=root.bodyX; z: 4 }
}
