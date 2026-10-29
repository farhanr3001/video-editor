import QtQuick
import QtMultimedia

Item {
    id: host
    property alias sink: video.videoSink
    property alias texture: captured
    property bool admitted: false
    property int pixelWidth: 1920
    property int pixelHeight: 1080
    width: pixelWidth; height: pixelHeight
    VideoOutput {
        id: video
        anchors.fill: parent
        fillMode: VideoOutput.Stretch
        endOfStreamPolicy: VideoOutput.KeepLastFrame
    }
    ShaderEffectSource {
        id: captured
        objectName: "texture"
        sourceItem: video
        hideSource: true
        visible: false
        live: host.admitted
        textureSize: Qt.size(host.pixelWidth, host.pixelHeight)
        smooth: true
        mipmap: true
    }
}
