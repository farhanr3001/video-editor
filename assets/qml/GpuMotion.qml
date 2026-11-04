import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

// GPU motion-graphics renderer. `frame` comes from kinetic_cut/motion_frame.py; every pixel is drawn by Qt Quick on the GPU
// (Shapes with the curve renderer, MultiEffect blur/glow/mask, and the motion_* shaders for bloom and the grade).
Item {
    id: root
    property var frame: ({ items: [], post: null, background: null })
    property real k: 1
    property real bloomScale: 0.25
    property real bloomBoost: 2.0
    property matrix4x4 placement: Qt.matrix4x4()
    property real alpha: 1
    clip: true
    opacity: alpha
    transform: Matrix4x4 { matrix: root.placement }
    readonly property var post: frame && frame.post ? frame.post : null

    // 1. scene content (background, floor reflection, layers) rendered at device size
    Item {
        id: content
        width: root.width; height: root.height
        Shape {
            visible: !!(root.frame.background)
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: root.frame.background && root.frame.background.color && !root.frame.background.gradient ? root.frame.background.color : "transparent"
                strokeColor: "transparent"
                fillGradient: bgRadial ? rg : lg
                PathRectangle { x: 0; y: 0; width: root.width; height: root.height }
            }
            LinearGradient {
                id: lg
                property real a: root.frame.background && root.frame.background.angle !== undefined ? root.frame.background.angle * Math.PI / 180 : Math.PI / 2
                x1: root.width / 2 - Math.cos(a) * root.width / 2; y1: root.height / 2 - Math.sin(a) * root.height / 2
                x2: root.width / 2 + Math.cos(a) * root.width / 2; y2: root.height / 2 + Math.sin(a) * root.height / 2
                GradientStop { position: 0; color: bgc(0) }
                GradientStop { position: 1; color: bgc(1) }
            }
            RadialGradient {
                id: rg
                centerX: (root.frame.background && root.frame.background.center ? root.frame.background.center[0] : .5) * root.width
                centerY: (root.frame.background && root.frame.background.center ? root.frame.background.center[1] : .45) * root.height
                centerRadius: Math.max(root.width, root.height) * (root.frame.background && root.frame.background.radius ? root.frame.background.radius : .75)
                focalX: centerX; focalY: centerY
                GradientStop { position: 0; color: bgc(0) }
                GradientStop { position: 1; color: bgc(1) }
            }
        }
        // floor reflection: the layers mirrored about the floor line, faded and softened on the GPU
        Item {
            id: reflection
            visible: !!root.frame.floor
            y: root.frame.floor ? root.frame.floor.y * root.k : 0
            width: root.width; height: root.frame.floor ? Math.max(1, Math.min(root.height - y, root.frame.floor.fade * root.k)) : 1
            layer.enabled: visible
            layer.effect: ShaderEffect { property var maskTex: fadeSrc; property real invert: 0; fragmentShader: "../shaders/motion_mask.frag.qsb" }
            Item {
                width: reflection.width; height: reflection.height
                clip: true
                layer.enabled: true
                layer.effect: MultiEffect { autoPaddingEnabled: false; blurEnabled: true; blurMax: 64; blur: root.frame.floor ? Math.min(1, root.frame.floor.blur * root.k / 64) : 0 }
                ShaderEffectSource {
                    y: -reflection.y; width: root.width; height: root.height
                    sourceItem: nodesItem; live: true; hideSource: false
                    transform: Scale { yScale: -1; origin.y: reflection.y }
                }
            }
        }
        Rectangle {
            id: fadeMask
            visible: false; width: root.width; height: reflection.height
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(1, 1, 1, root.frame.floor ? root.frame.floor.opacity : 0) }
                GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) }
            }
        }
        ShaderEffectSource { id: fadeSrc; sourceItem: fadeMask; live: true; visible: false; hideSource: true }
        Item {
            id: nodesItem
            width: root.width; height: root.height
            GpuMotionList { items: root.frame.items; k: root.k }
        }
    }
    readonly property bool bgRadial: !!(root.frame.background && root.frame.background.radial)
    function bgc(i) {
        var b = root.frame.background
        if (!b || !b.gradient || !b.gradient.length) return "transparent"
        return i === 0 ? b.gradient[0] : b.gradient[b.gradient.length - 1]
    }

    // 2. post chain: threshold -> three blurs -> combine, then one grade pass (vignette/grain/aberration/tint/contrast...)
    ShaderEffectSource { id: sceneSrc; sourceItem: content; live: true; visible: false; hideSource: !!root.post; textureSize: Qt.size(root.width, root.height) }
    ShaderEffect {
        id: bright
        visible: false; width: root.width; height: root.height
        property var source: sceneSrc
        property real threshold: root.post ? root.post.bloom_threshold : .55
        fragmentShader: "../shaders/motion_bright.frag.qsb"
    }
    ShaderEffectSource { id: brightSrc; sourceItem: bright; live: true; visible: false; hideSource: true; textureSize: Qt.size(Math.max(2, root.width * root.bloomScale), Math.max(2, root.height * root.bloomScale)) }
    function bloomR(n) { return root.post ? Math.max(1, root.post.bloom_radius * root.k * root.bloomScale) * (1 + 1.7 * (n - 1)) : 1 }
    MultiEffect { id: m1; visible: false; width: root.width * root.bloomScale; height: root.height * root.bloomScale; source: brightSrc; autoPaddingEnabled: false; blurEnabled: true; blurMax: 64; blur: Math.min(1, bloomR(1) / 64) }
    MultiEffect { id: m2; visible: false; width: root.width * root.bloomScale; height: root.height * root.bloomScale; source: brightSrc; autoPaddingEnabled: false; blurEnabled: true; blurMax: 64; blur: Math.min(1, bloomR(2) / 64) }
    MultiEffect { id: m3; visible: false; width: root.width * root.bloomScale; height: root.height * root.bloomScale; source: brightSrc; autoPaddingEnabled: false; blurEnabled: true; blurMax: 64; blur: Math.min(1, bloomR(3) / 64) }
    ShaderEffectSource { id: s1; sourceItem: m1; live: true; visible: false; hideSource: true }
    ShaderEffectSource { id: s2; sourceItem: m2; live: true; visible: false; hideSource: true }
    ShaderEffectSource { id: s3; sourceItem: m3; live: true; visible: false; hideSource: true }
    ShaderEffect {
        id: combine
        visible: false; width: root.width * root.bloomScale; height: root.height * root.bloomScale
        property var b1: s1; property var b2: s2; property var b3: s3
        fragmentShader: "../shaders/motion_bloom.frag.qsb"
    }
    ShaderEffectSource { id: bloomSrc; sourceItem: combine; live: true; visible: false; hideSource: true }
    ShaderEffect {
        id: grade
        visible: !!root.post
        width: root.width; height: root.height
        property var source: sceneSrc
        property var bloomTex: bloomSrc
        property real aberration: root.post ? root.post.aberration * root.k / Math.max(1, root.width) : 0
        property real bloomGain: root.post ? root.post.bloom * 1.6 * root.bloomBoost : 0
        property real brightness: root.post ? root.post.brightness : 0
        property real contrast: root.post ? root.post.contrast : 1
        property real saturation: root.post ? root.post.saturation : 1
        property real tintAmount: root.post ? root.post.tint_amount : 0
        property real vignette: root.post ? Math.min(1, root.post.vignette) : 0
        property real vignetteSoft: root.post ? root.post.vignette_softness : .6
        property real grain: root.post ? root.post.grain : 0
        property real seed: root.frame.seed ? root.frame.seed : 0
        property real aspect: root.width / Math.max(1, root.height)
        property color tintColor: root.post ? root.post.tint_rgb : "white"
        fragmentShader: "../shaders/motion_post.frag.qsb"
    }
}
