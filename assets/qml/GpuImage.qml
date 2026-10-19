import QtQuick
Image {
    property alias texture: image
    id: image
    objectName: "texture"
    visible: false
    cache: false
    retainWhileLoading: true
    fillMode: Image.Stretch
}
