// Included by qt_media_engine.cpp. Scene preparation is native, during Qt sync;
// shader composition runs on the render thread. No QML per-clip layout bindings.
#include <QtCore/QThreadPool>
#include <QtGui/QImageReader>
#include <QtGui/QFontMetrics>
#include <QtQuick/QSGGeometryNode>
#include <QtQuick/QSGMaterial>
#include <QtQuick/QSGTexture>
#include <QtQuick/QSGSimpleTextureNode>
#include <map>
#include <vector>
#include <array>
#include <algorithm>

struct ClipInput {
    double start,duration,y,height,top,bottom,in,speed,gain,fadeIn,fadeOut,aspect;
    unsigned long long wave;double waveCount,waveResolution;
    unsigned color,flags;const char* label;const char* thumbnail;
};
struct ClipData:ClipInput {QString name,path;};
struct Asset {QImage image;unsigned version=0;bool pending=false;unsigned long long used=0;};
struct Assets {std::mutex lock;std::map<QString,Asset> images;std::map<unsigned long long,Asset> waves;std::atomic<unsigned> version{0};};
static QString clipShaderPath;
struct ClipMaterial:QSGMaterial {
    QSGTexture* thumb=nullptr;QSGTexture* wave=nullptr;
    std::array<float,28> values{};
    ClipMaterial(){setFlag(Blending);setFlag(RequiresFullMatrix);setFlag(NoBatching);}
    QSGMaterialType* type()const override{static QSGMaterialType type;return &type;}
    int compare(const QSGMaterial* other)const override{return this==other?0:(this<other?-1:1);}
    QSGMaterialShader* createShader(QSGRendererInterface::RenderMode)const override;
};
class ClipShader:public QSGMaterialShader {
public:
    ClipShader(){setShaderFileName(VertexStage,clipShaderPath+QStringLiteral("/native_clip.vert.qsb"));setShaderFileName(FragmentStage,clipShaderPath+QStringLiteral("/native_clip.frag.qsb"));}
    bool updateUniformData(RenderState& state,QSGMaterial* next,QSGMaterial*)override{
        auto material=static_cast<ClipMaterial*>(next);auto data=state.uniformData();
        if(data->size()<192)data->resize(192);
        memcpy(data->data(),state.combinedMatrix().constData(),64);
        float opacity=state.opacity();memcpy(data->data()+64,&opacity,4);memcpy(data->data()+80,material->values.data(),112);return true;
    }
    void updateSampledImage(RenderState& state,int binding,QSGTexture** texture,QSGMaterial* next,QSGMaterial*)override{
        auto material=static_cast<ClipMaterial*>(next);*texture=binding==1?material->thumb:material->wave;
        if(*texture){
            (*texture)->setFiltering(binding==1?QSGTexture::Linear:QSGTexture::Nearest);
            // createTextureFromImage defers the GPU allocation/upload. Custom
            // materials must commit it before the renderer binds the sampler.
            // Without this even the solid clip body is skipped by the RHI.
            (*texture)->commitTextureOperations(state.rhi(),state.resourceUpdateBatch());
        }
    }
};
QSGMaterialShader* ClipMaterial::createShader(QSGRendererInterface::RenderMode)const{return new ClipShader();}
struct ClipRoot:QSGNode {
    QSGNode* content=new QSGNode();
    struct Texture {std::unique_ptr<QSGTexture> image;unsigned version=0,used=0;size_t bytes=0;};
    std::map<QString,Texture> textures;
    std::unique_ptr<QSGTexture> blank;
    unsigned generation=0,assets=0,reset=0,frame=0;double pps=-1,offset=-1,width=-1,height=-1;
    ClipRoot(){appendChildNode(content);}
};
class ClipCanvas:public QQuickItem {
public:
    double pps=20,offset=0;unsigned generation=1,reset=0;
    std::vector<ClipData> clips;std::shared_ptr<Assets> assets=std::make_shared<Assets>();
    unsigned seenAssets=0;unsigned long long seenImage=0;
    explicit ClipCanvas(QQuickItem* parent):QQuickItem(parent){setFlag(ItemHasContents);}
    void image(const QString& path){
        if(path.isEmpty())return;auto shared=assets;
        {std::lock_guard<std::mutex> lock(shared->lock);auto& asset=shared->images[path];asset.used=++seenImage;if(asset.pending||asset.version)return;asset.pending=true;}
        QThreadPool::globalInstance()->start([shared,path]{
            QImageReader reader(path);reader.setAutoTransform(true);auto size=reader.size();if(size.isValid())reader.setScaledSize(size.scaled(QSize(320,180),Qt::KeepAspectRatio));
            auto image=reader.read();std::lock_guard<std::mutex> lock(shared->lock);auto& asset=shared->images[path];asset.image=image;asset.version=++shared->version;asset.pending=false;
        });
    }
protected:
    QSGNode* updatePaintNode(QSGNode* previous,UpdatePaintNodeData*)override{
        auto root=static_cast<ClipRoot*>(previous);if(!root)root=new ClipRoot();
        auto av=assets->version.load();
        if(root->generation==generation&&root->pps==pps&&root->offset==offset&&root->width==width()&&root->height==height()&&root->assets==av)return root;
        while(auto child=root->content->firstChild()){root->content->removeChildNode(child);delete child;}
        if(root->reset!=reset){root->textures.clear();root->reset=reset;}
        ++root->frame;
        if(!root->blank){QImage blank(1,1,QImage::Format_RGBA8888);blank.fill(Qt::white);root->blank.reset(window()->createTextureFromImage(blank));}
        auto texture=[&](const QString& key,const Asset& asset)->QSGTexture*{
            if(asset.image.isNull())return root->blank.get();auto& entry=root->textures[key];
            if(!entry.image||entry.version!=asset.version){entry.image.reset(window()->createTextureFromImage(asset.image));entry.version=asset.version;}
            entry.used=root->frame;entry.bytes=asset.image.sizeInBytes();
            return entry.image.get();
        };
        std::map<QString,Asset> images;std::map<unsigned long long,Asset> waves;
        {
            std::lock_guard<std::mutex> lock(assets->lock);
            // Only copy assets referenced by this viewport snapshot. Visited
            // media elsewhere in a long project are not per-frame work.
            for(const auto& clip:clips){
                auto image=assets->images.find(clip.path);if(image!=assets->images.end())images.emplace(image->first,image->second);
                auto wave=assets->waves.find(clip.wave);if(wave!=assets->waves.end())waves.emplace(wave->first,wave->second);
            }
            auto icon=assets->waves.find(~0ULL);if(icon!=assets->waves.end())waves.emplace(icon->first,icon->second);
            while(assets->images.size()>256){
                auto oldest=assets->images.end();
                for(auto it=assets->images.begin();it!=assets->images.end();++it)
                    if(!it->second.pending&&!images.count(it->first)&&(oldest==assets->images.end()||it->second.used<oldest->second.used))oldest=it;
                if(oldest==assets->images.end())break;assets->images.erase(oldest);
            }
        }
        for(const auto& clip:clips){
            double x=clip.start*pps-offset,w=std::max(5.,clip.duration*pps);
            if(x+w<-4||x>width()+4||clip.y+clip.height<clip.top||clip.y>clip.bottom)continue;
            auto section=new QSGClipNode();section->setIsRectangular(true);section->setClipRect(QRectF(0,std::max(0.,clip.top),width(),std::max(0.,std::min(height(),clip.bottom)-std::max(0.,clip.top))));root->content->appendChildNode(section);
            auto node=new QSGGeometryNode();auto geometry=new QSGGeometry(QSGGeometry::defaultAttributes_TexturedPoint2D(),4);geometry->setDrawingMode(QSGGeometry::DrawTriangleStrip);
            QSGGeometry::updateTexturedRectGeometry(geometry,QRectF(x,clip.y,w,clip.height),QRectF(0,0,1,1));node->setGeometry(geometry);node->setFlag(QSGNode::OwnsGeometry);
            auto material=new ClipMaterial();node->setMaterial(material);node->setFlag(QSGNode::OwnsMaterial);section->appendChildNode(node);
            auto base=QColor::fromRgba(clip.color);if(clip.flags&2)base=base.lighter(112);
            auto border=QColor((clip.flags&2)?QStringLiteral("#f05a50"):QStringLiteral("#08090b"));
            auto setColor=[&](int at,QColor c){material->values[at]=c.redF()*c.alphaF();material->values[at+1]=c.greenF()*c.alphaF();material->values[at+2]=c.blueF()*c.alphaF();material->values[at+3]=c.alphaF();};
            setColor(0,base);setColor(4,border);
            material->thumb=root->blank.get();material->wave=root->blank.get();
            bool hasThumb=!clip.path.isEmpty()&&images.count(clip.path)&&!images[clip.path].image.isNull();
            if(hasThumb)material->thumb=texture(clip.path,images[clip.path]);
            Asset wave;if(waves.count(clip.wave)){wave=waves[clip.wave];material->wave=texture(QStringLiteral("wave:%1").arg(clip.wave),wave);}
            float values[]={float(clip.in),float(clip.speed),float(clip.waveResolution),float(wave.image.isNull()?0:clip.waveCount),
                float(clip.duration),float(clip.fadeIn),float(clip.fadeOut),float(clip.gain),
                float(w),float(clip.height),float(std::max(1.,(clip.height-25)*clip.aspect)),float(std::max(1,wave.image.width())),
                float(std::max(1,wave.image.height())),0,float(hasThumb),0,
                float(pps),0,float(clip.flags),0};
            std::copy(values,values+20,material->values.begin()+8);
            bool textItem=clip.flags&(256|1024);
            if(w>=44||(textItem&&w>=14)){
                auto mask=new QSGClipNode();mask->setIsRectangular(true);mask->setClipRect(QRectF(x+4,clip.y+2,std::max(0.,w-8),std::max(0.,clip.height-4)));section->appendChildNode(mask);
                auto label=window()->createTextNode();label->setColor(QColor(textItem?QStringLiteral("#151515"):QStringLiteral("white")));mask->appendChildNode(label);
                QFont font(QStringLiteral("Segoe UI"));font.setPointSize(9);
                bool linked=(clip.flags&64)&&w>=110;
                auto name=textItem?clip.name:QFontMetrics(font).elidedText(clip.name,Qt::ElideRight,std::max(0,int(w-12-(linked?22:0))));
                bool strip=(clip.flags&1)||(hasThumb&&w>=28&&clip.height>=52);
                double top=strip?clip.y+clip.height-((clip.flags&1)?20:21):clip.y;
                double height=strip?((clip.flags&1)?19:20):clip.height;
                if(textItem){
                    font.setPixelSize(11);font.setWeight(QFont::DemiBold);
                    name.replace(QChar('\n'),QChar(0x2028));
                    QTextLayout layout(name,font);QTextOption option;option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);
                    const double lineHeight=QFontMetricsF(font).height();const double inset=(clip.flags&1024)?14.:4.;double y=0;layout.beginLayout();
                    while(y+lineHeight<=clip.height-inset-3){auto line=layout.createLine();if(!line.isValid())break;line.setLineWidth(std::max(1.,w-8));line.setPosition(QPointF(0,y));y+=line.height();}
                    layout.endLayout();label->addTextLayout(QPointF(x+4,clip.y+inset),&layout);
                }else{
                    QTextLayout layout(name,font);layout.beginLayout();auto line=layout.createLine();line.setLineWidth(std::max(1.,w-12-(linked?22:0)));layout.endLayout();
                    label->addTextLayout(QPointF(x+6,top+(height-layout.boundingRect().height())/2),&layout);
                }
                if((clip.flags&128)&&w>70){section->appendChildNode(new QSGSimpleRectNode(QRectF(std::max(x+5,5.),clip.y+12,22,15),QColor(QStringLiteral("#202833"))));auto badge=window()->createTextNode();badge->setColor(QColor(QStringLiteral("#afc6e1")));section->appendChildNode(badge);text(badge,QStringLiteral("fx"),QPointF(std::max(x+9,9.),clip.y+12),10,true);}
                if(linked&&waves.count(~0ULL)){
                    auto icon=new QSGSimpleTextureNode();icon->setTexture(texture(QStringLiteral("ui:link"),waves[~0ULL]));
                    icon->setRect(QRectF(x+w-20,clip.y+clip.height-19,13,13));mask->appendChildNode(icon);
                }
            }
        }
        size_t bytes=0;for(const auto& pair:root->textures)bytes+=pair.second.bytes;
        while(bytes>96*1024*1024){
            auto oldest=root->textures.end();
            for(auto it=root->textures.begin();it!=root->textures.end();++it)
                if(it->second.used!=root->frame&&(oldest==root->textures.end()||it->second.used<oldest->second.used))oldest=it;
            if(oldest==root->textures.end())break;bytes-=oldest->second.bytes;root->textures.erase(oldest);
        }
        root->generation=generation;root->assets=av;root->pps=pps;root->offset=offset;root->width=width();root->height=height();
        return root;
    }
};
API void* kc_clips_create(void* parent,const char* shaders){if(!parent)return nullptr;clipShaderPath=QString::fromUtf8(shaders);return new ClipCanvas(static_cast<QQuickItem*>(parent));}
API void kc_clips_view(void* handle,double width,double height,double pps,double offset){
    if(!handle)return;auto item=static_cast<ClipCanvas*>(handle);auto av=item->assets->version.load();
    if(item->width()==width&&item->height()==height&&item->pps==pps&&item->offset==offset&&item->seenAssets==av)return;
    item->seenAssets=av;item->setWidth(width);item->setHeight(height);item->pps=pps;item->offset=offset;item->update();
}
API void kc_clips_set(void* handle,const ClipInput* inputs,unsigned count){
    if(!handle)return;auto item=static_cast<ClipCanvas*>(handle);item->clips.clear();item->clips.reserve(count);
    for(unsigned n=0;n<count;++n){ClipData clip;static_cast<ClipInput&>(clip)=inputs[n];clip.name=QString::fromUtf8(inputs[n].label);clip.path=QString::fromUtf8(inputs[n].thumbnail);clip.label=nullptr;clip.thumbnail=nullptr;item->image(clip.path);item->clips.push_back(std::move(clip));}
    ++item->generation;item->update();
}
API void kc_clips_image(void* handle,unsigned long long key,void* pointer){
    if(!handle||!pointer)return;auto item=static_cast<ClipCanvas*>(handle);std::lock_guard<std::mutex> lock(item->assets->lock);auto& asset=item->assets->waves[key];asset.image=*static_cast<QImage*>(pointer);asset.version=++item->assets->version;item->update();
}
API void kc_clips_reset(void* handle){
    if(!handle)return;auto item=static_cast<ClipCanvas*>(handle);
    item->assets=std::make_shared<Assets>();item->clips.clear();++item->reset;++item->generation;item->update();
}
