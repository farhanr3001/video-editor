# Lens Studio template pack: Kinetic Cut compatibility review

Reviewed 24 September 2026: `C:\Users\F\Downloads\lens-studio-templates-main\lens-studio-templates-main`, especially its 19 `Face/` projects.

The pack is a collection of **Lens Studio projects**, not a library of standalone, permissively licensed face filters. Every Face project carries `LICENSE.txt` referring to Snap's [Lens Studio Template License](https://lensstudio.snapchat.com/template-license). The repository does not have a general MIT/Apache-style license; a public GitHub checkout is not, by itself, permission to embed its models, artwork, scripts and materials in Kinetic Cut. The linked full template-license text was unavailable during this review, so no Snap asset has been copied into the distributable application.

Technically, the projects use Lens Studio scene and material formats (`.lsproj`, `.mesh`, `.lsmat`, animation textures and runtime scripts). `.mesh` and `.lsmat` are [Lens Studio project formats](https://developers.snap.com/lens-studio/lens-studio-workflow/advanced/source-control), not GLB/FBX files directly loadable by Kinetic Cut's model-view builder. They also rely on Snap's face tracking, face mesh, segmentation, materials and/or script APIs. Copying their files to our effects folder would produce non-functional entries. Kinetic Cut's MediaPipe worker and FFmpeg/Qt renderer are independent implementations.

| Face template | Relevant idea | Direct port status |
| --- | --- | --- |
| 2D Objects | Face-following overlays | Requires original/licensed art and recreation of attachment logic. |
| 3D Objects | Face-attached props | 22 native `.mesh` files; cannot be directly rendered by the current GLB-view pipeline. |
| Baseball Cap | Tracked headwear | Four native cap meshes/materials; needs separately licensed GLB and fit/occlusion QA. |
| Chain Physics | Moving accessory | Requires physics and frame-to-frame state; not a portable static asset. |
| Countdown | Interactive time graphic | Not primarily a face filter; Kinetic Cut already has a timer graphic. |
| Distort | Facial reshaping | Concept covered independently by **Custom Face** and existing morph filters. |
| Face in Picture / Face in Video | Face replacement | Requires source/target face compositing, alignment and quality work, not simple asset import. |
| Face Mesh | 3D face material | Lens Studio-specific mesh and material; Kinetic Cut now records 478 MediaPipe landmarks, but not Snap's render mesh. |
| Face Paint / Makeup / Photo | Tracked cosmetics/retouch | Requires independently licensed looks and detailed UV/masking implementation. |
| Hair Color | Hair segmentation and recolour | Needs a reliable hair-specific mask model (the current selfie segmentation model only isolates the person). |
| Paper Head | Stylized head replacement | Native materials/textures and scene setup; not directly portable. |
| Portrait Particles | Particle emission around face | Requires particle simulation, determinism and export parity. |
| Segmentation | Person/background effects | Already implemented independently as Remove Person Background. |
| Sunglasses | Tracked eyewear | 35 native `.mesh` files; Kinetic Cut already offers separately sourced **AR Pixel Glasses**. |
| Team Celebrate / Trigger | Multi-face or expression-triggered actions | Needs expression/event data and temporal state; not a drop-in filter. |

The Face Filters browser is grouped by available effect type: Face shape & colour, Animal filters, Glasses and Masks. These are **browser-only** groups; saved effect names, projects, drag/drop and automation are unchanged. An empty Hats group was deliberately not added. New independently licensed GLB hats/eyewear/masks can be inspected, calibrated, rendered and added to a matching group; obtain the asset license and check each pose on real footage before shipping it.
