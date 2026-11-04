import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

// Draws one list of frame-description items (see kinetic_cut/motion_frame.py) on the GPU. Everything is in device pixels.
Item {
    id: list
    property var items: []
    property real k: 1
    property real blurMax: 64
    width: parent ? parent.width : 0
    height: parent ? parent.height : 0

    function mx(m) { return Qt.matrix4x4(m[0], m[2], 0, m[4], m[1], m[3], 0, m[5], 0, 0, 1, 0, 0, 0, 0, 1) }

    Repeater {
        model: list.items.length
        delegate: Loader {
            id: slot
            property var d: list.items[index]
            property string kind: d ? d.k : ""
            width: list.width; height: list.height
            onLoaded: item.d = Qt.binding(function() { return slot.d })
            sourceComponent: kind === "path" ? pathC : kind === "layer" ? layerC : kind === "dblur" ? dblurC : kind === "clip" ? clipC : kind === "image" ? imageC : kind === "video" ? videoC : kind === "trail" ? trailC : kind === "particles" ? particlesC : undefined
        }
    }

    Component {
        id: pathC
        Item {
            id: node
            property var d: null
            property var f: d ? d.fill : null
            property var s: d ? d.stroke : null
            width: list.width; height: list.height
            opacity: d.opacity
            layer.enabled: !!d && d.blur > 0.05
            layer.effect: MultiEffect { blurEnabled: true; blurMax: list.blurMax; blur: Math.min(1, d.blur * list.k / list.blurMax) }
            Shape {
                id: shape
                preferredRendererType: Shape.CurveRenderer
                transform: Matrix4x4 { matrix: list.mx(d.matrix) }
                ShapePath {
                    fillRule: ShapePath.WindingFill  // SVG nonzero: overlapping sub-shapes merge instead of punching holes
                    fillColor: f && f.type === "solid" ? f.color : "transparent"
                    fillGradient: f && f.type === "linear" ? lin : f && f.type === "radial" ? rad : null
                    strokeColor: s ? s.color : "transparent"
                    strokeWidth: s ? s.width : 0
                    capStyle: s && s.cap === "flat" ? ShapePath.FlatCap : s && s.cap === "square" ? ShapePath.SquareCap : ShapePath.RoundCap
                    joinStyle: s && s.join === "miter" ? ShapePath.MiterJoin : s && s.join === "bevel" ? ShapePath.BevelJoin : ShapePath.RoundJoin
                    strokeStyle: s && s.dash ? ShapePath.DashLine : ShapePath.SolidLine
                    dashPattern: s && s.dash ? s.dash : []
                    dashOffset: s && s.offset ? s.offset : 0
                    PathSvg { path: d.d ? d.d : "" }
                }
            }
            LinearGradient { id: lin; x1: f && f.x1 !== undefined ? f.x1 : 0; y1: f && f.y1 !== undefined ? f.y1 : 0; x2: f && f.x2 !== undefined ? f.x2 : 0; y2: f && f.y2 !== undefined ? f.y2 : 0
                GradientStop { position: f && f.stops ? f.stops[0][0] : 0; color: f && f.stops ? f.stops[0][1] : "transparent" }
                GradientStop { position: f && f.stops ? f.stops[Math.min(1, f.stops.length - 1)][0] : 1; color: f && f.stops ? f.stops[Math.min(1, f.stops.length - 1)][1] : "transparent" }
                GradientStop { position: f && f.stops ? f.stops[Math.min(2, f.stops.length - 1)][0] : 1; color: f && f.stops ? f.stops[Math.min(2, f.stops.length - 1)][1] : "transparent" }
                GradientStop { position: f && f.stops ? f.stops[Math.min(3, f.stops.length - 1)][0] : 1; color: f && f.stops ? f.stops[Math.min(3, f.stops.length - 1)][1] : "transparent" }
            }
            RadialGradient { id: rad; centerX: f && f.cx !== undefined ? f.cx : 0; centerY: f && f.cy !== undefined ? f.cy : 0; centerRadius: f && f.r ? f.r : 1; focalX: centerX; focalY: centerY
                GradientStop { position: f && f.stops ? f.stops[0][0] : 0; color: f && f.stops ? f.stops[0][1] : "transparent" }
                GradientStop { position: f && f.stops ? f.stops[Math.min(1, f.stops.length - 1)][0] : 1; color: f && f.stops ? f.stops[Math.min(1, f.stops.length - 1)][1] : "transparent" }
                GradientStop { position: f && f.stops ? f.stops[Math.min(2, f.stops.length - 1)][0] : 1; color: f && f.stops ? f.stops[Math.min(2, f.stops.length - 1)][1] : "transparent" }
                GradientStop { position: f && f.stops ? f.stops[Math.min(3, f.stops.length - 1)][0] : 1; color: f && f.stops ? f.stops[Math.min(3, f.stops.length - 1)][1] : "transparent" }
            }
        }
    }

    Component {
        id: dblurC
        Item {
            property var d: null
            width: list.width; height: list.height
            layer.enabled: true
            layer.effect: ShaderEffect {
                property vector2d sigma: Qt.vector2d(d ? d.dx * list.k / Math.max(1, list.width) : 0, d ? d.dy * list.k / Math.max(1, list.height) : 0)
                fragmentShader: "../shaders/motion_dirblur.frag.qsb"
            }
            Loader {
                width: list.width; height: list.height
                source: "GpuMotionList.qml"
                onLoaded: { item.items = Qt.binding(function() { return d ? d.items : [] }); item.k = Qt.binding(function() { return list.k }) }
            }
        }
    }

    Component {
        id: layerC
        Item {
            id: outer
            property var d: null
            property var g: d ? d.glow : null
            width: list.width; height: list.height
            opacity: d ? d.opacity : 1
            // add / screen: premultiplied colour with zero alpha makes normal blending an additive GPU blend
            layer.enabled: !!d && (d.blend === "add" || d.blend === "screen")
            layer.effect: ShaderEffect { property real gain: 1; fragmentShader: "../shaders/motion_add.frag.qsb" }

            // glow halo: progressively wider blurs of the layer added on top (all on the GPU)
            Item {
                id: halo
                visible: !!g
                width: list.width; height: list.height
                layer.enabled: !!g
                layer.effect: ShaderEffect { property real gain: g ? 1.4 * g.intensity / Math.sqrt(Math.max(1, g.layers)) : 0; fragmentShader: "../shaders/motion_add.frag.qsb" }
                Repeater {
                    model: g ? g.layers : 0
                    delegate: MultiEffect {
                        width: list.width; height: list.height
                        source: haloSrc
                        opacity: 1 / (1 + .6 * index)
                        autoPaddingEnabled: false
                        blurEnabled: true; blurMax: list.blurMax
                        blur: g ? Math.min(1, g.radius * list.k * (1 + 1.8 * index) / list.blurMax) : 0
                        colorization: g && g.color ? 1 : 0
                        colorizationColor: g && g.color ? g.color : "white"
                    }
                }
            }
            Item {
                id: maskWrap
                width: list.width; height: list.height
                layer.enabled: !!(d && d.mask)
                layer.effect: ShaderEffect {
                    property var maskTex: maskSrc
                    property real invert: d && d.mask && d.mask.invert ? 1 : 0
                    fragmentShader: "../shaders/motion_mask.frag.qsb"
                }
            Item {
                id: inner
                width: list.width; height: list.height
                layer.enabled: true
                layer.effect: MultiEffect {
                    autoPaddingEnabled: false
                    blurEnabled: !!d && d.blur > 0.05
                    blurMax: list.blurMax
                    blur: d ? Math.min(1, d.blur * list.k / list.blurMax) : 0
                    shadowEnabled: !!(d && d.shadow)
                    shadowColor: d && d.shadow ? d.shadow.color : "black"
                    shadowOpacity: d && d.shadow ? d.shadow.opacity : 0
                    shadowBlur: d && d.shadow ? Math.min(1, d.shadow.blur / 64) : 0
                    shadowHorizontalOffset: d && d.shadow ? d.shadow.dx : 0
                    shadowVerticalOffset: d && d.shadow ? d.shadow.dy : 0
                }
                Loader {
                    width: list.width; height: list.height
                    source: "GpuMotionList.qml"
                    onLoaded: { item.items = Qt.binding(function() { return d ? d.items : [] }); item.k = Qt.binding(function() { return list.k }) }
                }
            }
            }
            ShaderEffectSource { id: haloSrc; sourceItem: inner; live: true; visible: false; hideSource: false; width: list.width; height: list.height }
            Item {
                id: shapeHost
                width: list.width; height: list.height
                Shape {
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath { fillRule: ShapePath.WindingFill; fillColor: "white"; strokeColor: "transparent"; PathSvg { path: d && d.mask ? d.mask.d : "" } }
                }
            }
            ShaderEffectSource { id: shapeSrc; sourceItem: shapeHost; hideSource: true; live: true; visible: false; width: list.width; height: list.height }
            MultiEffect {
                id: maskBlur
                width: list.width; height: list.height
                source: shapeSrc
                autoPaddingEnabled: false
                blurEnabled: !!(d && d.mask && d.mask.feather > 0); blurMax: list.blurMax
                blur: d && d.mask ? Math.min(1, d.mask.feather * 1.5 * list.k / list.blurMax) : 0
            }
            ShaderEffectSource { id: maskSrc; sourceItem: maskBlur; hideSource: true; live: true; visible: false; width: list.width; height: list.height }
        }
    }

    Component {
        id: clipC
        Item {
            property var d: null
            width: list.width; height: list.height
            opacity: d ? d.opacity : 1
            transform: Matrix4x4 { matrix: d ? list.mx(d.matrix) : Qt.matrix4x4() }
            Item {
                x: d ? d.rect[0] : 0; y: d ? d.rect[1] : 0; width: d ? d.rect[2] : 0; height: d ? d.rect[3] : 0
                clip: true
                Item {
                    x: d ? -d.rect[0] : 0; y: d ? -d.rect[1] : 0
                    width: list.width; height: list.height
                    Loader {
                        width: list.width; height: list.height
                        source: "GpuMotionList.qml"
                        onLoaded: { item.items = Qt.binding(function() { return d ? d.items : [] }); item.k = Qt.binding(function() { return list.k }) }
                    }
                }
            }
        }
    }

    Component {
        id: videoC
        Item {
            property var d: null
            width: list.width; height: list.height
            opacity: d ? d.opacity : 1
            Item {
                transform: Matrix4x4 { matrix: d ? list.mx(d.matrix) : Qt.matrix4x4() }
                Item {
                    x: d ? -d.w / 2 : 0; y: d ? -d.h / 2 : 0; width: d ? d.w : 0; height: d ? d.h : 0
                    clip: d ? d.fit === "cover" : false
                    Image {
                        // decoded frame-accurately by kinetic_cut/motion_video.py, drawn here as a GPU texture
                        anchors.fill: parent
                        source: d && d.source ? "image://motionvideo/" + encodeURIComponent(d.source) + "?t=" + d.t.toFixed(4) : ""
                        asynchronous: false; cache: false; smooth: true; retainWhileLoading: true
                        fillMode: d && d.fit === "contain" ? Image.PreserveAspectFit : d && d.fit === "cover" ? Image.PreserveAspectCrop : Image.Stretch
                    }
                }
            }
        }
    }

    Component {
        id: imageC
        Item {
            property var d: null
            width: list.width; height: list.height
            opacity: d ? d.opacity : 1
            Item {
                transform: Matrix4x4 { matrix: d ? list.mx(d.matrix) : Qt.matrix4x4() }
                Item {
                    x: d ? -d.w / 2 : 0; y: d ? -d.h / 2 : 0; width: d ? d.w : 0; height: d ? d.h : 0
                    clip: d ? d.fit === "cover" : false
                    Image {
                        anchors.fill: parent
                        source: d && d.source ? "file:///" + d.source.replace(/\\/g, "/") : ""
                        asynchronous: false; mipmap: true; smooth: true
                        fillMode: d && d.fit === "contain" ? Image.PreserveAspectFit : d && d.fit === "cover" ? Image.PreserveAspectCrop : Image.Stretch
                    }
                }
            }
        }
    }

    Component {
        id: trailC
        Item {
            id: trail
            property var d: null
            width: list.width; height: list.height
            opacity: d.opacity
            layer.enabled: !!(d && d.additive)
            layer.effect: ShaderEffect { property real gain: 1; fragmentShader: "../shaders/motion_add.frag.qsb" }
            Item {
                transform: Matrix4x4 { matrix: list.mx(d.matrix) }
                Repeater {
                    model: d.segments.length
                    delegate: Rectangle {
                        property var sg: d.segments[index]
                        property real dx: sg[2] - sg[0]
                        property real dy: sg[3] - sg[1]
                        x: sg[0]; y: sg[1] - sg[5] / 2
                        width: Math.sqrt(dx * dx + dy * dy) + sg[5]
                        height: sg[5]; radius: sg[5] / 2
                        color: sg[4]
                        transformOrigin: Item.Left
                        rotation: Math.atan2(dy, dx) * 180 / Math.PI
                        // extend the cap back so round joints overlap like a stroked polyline
                        transform: Translate { x: -sg[5] / 2 }
                    }
                }
            }
        }
    }

    Component {
        id: particlesC
        Item {
            id: cloud
            property var d: null
            width: list.width; height: list.height
            opacity: d.opacity
            layer.enabled: !!(d && d.additive)
            layer.effect: ShaderEffect { property real gain: 1; fragmentShader: "../shaders/motion_add.frag.qsb" }
            Item {
                transform: Matrix4x4 { matrix: list.mx(d.matrix) }
                Repeater {
                    model: d.list.length
                    delegate: Item {
                        property var p: d.list[index]
                        property real sz: p[4]
                        property bool line: p[6] === "spark" || p[6] === "streak"
                        Rectangle { // streak
                            visible: parent.line
                            property real lx: p[2]; property real ly: p[3]
                            x: p[0] - lx; y: p[1] - ly - Math.max(.5, sz) / 2
                            width: Math.sqrt(lx * lx + ly * ly); height: Math.max(.5, sz); radius: height / 2
                            color: p[5]; transformOrigin: Item.Left; rotation: Math.atan2(ly, lx) * 180 / Math.PI
                        }
                        Rectangle { // dot, spark head or ring
                            property real r: p[6] === "ring" ? sz * (1 + 3 * 0) : Math.max(.4, sz * (p[6] === "spark" ? .6 : .5))
                            visible: p[6] !== "streak"
                            x: p[0] - r; y: p[1] - r; width: r * 2; height: r * 2; radius: r
                            color: p[6] === "ring" ? "transparent" : p[5]
                            border.width: p[6] === "ring" ? Math.max(.5, sz * .3) : 0
                            border.color: p[5]
                        }
                    }
                }
            }
        }
    }
}
