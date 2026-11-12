import QtQuick

Rectangle {
    id: monitor
    color: "#101114"
    property real aspect: 1.7778
    property bool still: false
    property string message: "Opening clip…"
    readonly property bool imageReady: photo.status === Image.Ready
    GpuSource { id: video; objectName: "gradeVideo" }
    GpuImage { id: photo; objectName: "gradePhoto"; minification: true; asynchronous: true }
    GpuLayer {
        objectName: "gradeLayer"
        anchors.centerIn: parent
        width: Math.min(parent.width, parent.height * monitor.aspect)
        height: width / monitor.aspect
        texture: monitor.still ? photo : video.texture
    }
    Text {
        anchors.centerIn: parent
        color: "#eceef2"
        text: !monitor.still ? monitor.message :
              monitor.imageReady ? "" :
              photo.status === Image.Error ? "Could not open this image." : monitor.message
        visible: text.length > 0
    }
}
