// Qt owns GPU textures and decoding. Python never executes on media/render threads.
#include <QtCore/QCoreApplication>
#include <QtCore/QThread>
#include <QtCore/QTimer>
#include <QtCore/QPointer>
#include <QtCore/QEvent>
#include <QtCore/QUrl>
#include <QtQuick/QQuickWindow>
#include <QtQuick/QSGRendererInterface>
#include <QtQuick/QQuickItem>
#include <QtQuick/QSGSimpleRectNode>
#include <QtQuick/QSGTextNode>
#include <QtGui/QTextLayout>
#include <QtGui/6.11.2/QtGui/rhi/qrhi.h>
#include <QtMultimedia/QMediaPlayer>
#include <QtMultimedia/QVideoSink>
#include <QtMultimedia/QVideoFrame>
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <string>
#include <cmath>
#include <vector>
#include <algorithm>
using Clock=std::chrono::steady_clock;
static std::atomic<unsigned> activePlayers{0};
static double nowMs(){return std::chrono::duration<double,std::milli>(Clock::now().time_since_epoch()).count();}
static double ms(Clock::time_point a,Clock::time_point b){return std::chrono::duration<double,std::milli>(b-a).count();}
#define API extern "C" __declspec(dllexport)

struct FrameProbe {
    std::atomic<unsigned long long> serial{0},epoch{0};std::atomic<bool> active{false};
    unsigned long long previous=0,generation=0;bool sampling=false;
    QMetaObject::Connection connection;
};
struct RenderStats {
    std::atomic<unsigned long long> frames{0};
    std::atomic<double> record{0},synchronize{0},submit{0},gpu{-1};
    Clock::time_point begin,sync,render;
    std::mutex probeMutex;std::vector<std::shared_ptr<FrameProbe>> probes;
    std::atomic<unsigned long long> replaced{0},observed{0};
    std::atomic<bool> inFlight{false};
    std::atomic<unsigned long long> deferred{0};
    void sampleSources(){
        std::lock_guard<std::mutex> lock(probeMutex);
        for(const auto& probe:probes){
            auto serial=probe->serial.load(),epoch=probe->epoch.load();
            if(!probe->active){probe->sampling=false;probe->previous=serial;continue;}
            if(!probe->sampling||probe->generation!=epoch){probe->sampling=true;probe->generation=epoch;probe->previous=serial;continue;}
            auto count=serial-probe->previous;probe->previous=serial;observed+=count;
            if(count>1)replaced+=count-1;
        }
    }
    void prepare(QQuickWindow* window){
        render=Clock::now();
        // Qt RHI timestamps bracket the actual submitted command buffer. Timing
        // an immediate D3D context outside Qt's deferred list would report zero.
        if(auto chain=window->swapChain())if(auto commands=chain->currentFrameCommandBuffer()){
            auto seconds=commands->lastCompletedGpuTime();if(seconds>0)gpu=seconds*1000.;
        }
    }
    void complete(){
        record=ms(render,Clock::now());
    }
    void reset(){gpu=-1;inFlight=false;}
};
// Qt's threaded loop blocks the GUI in polishAndSync until the render thread
// accepts the next scene. Do not enter that wait while a prior frame is still
// being submitted/presented. Keep one retry, not one event per obsolete frame.
class RenderAdmission:public QObject {
    QPointer<QQuickWindow> window;std::shared_ptr<RenderStats> state;QTimer retry;
public:
    RenderAdmission(QQuickWindow* w,std::shared_ptr<RenderStats> s):QObject(w),window(w),state(s){
        retry.setSingleShot(true);retry.setTimerType(Qt::PreciseTimer);retry.setInterval(4);
        QObject::connect(&retry,&QTimer::timeout,this,[this]{
            if(!window||!window->isExposed())return;
            if(state->inFlight)retry.start();else window->requestUpdate();
        });w->installEventFilter(this);
    }
    bool eventFilter(QObject* watched,QEvent* event) override {
        if(watched==window&&event->type()==QEvent::UpdateRequest&&state->inFlight){
            ++state->deferred;if(!retry.isActive())retry.start();return true;
        }
        return QObject::eventFilter(watched,event);
    }
};
struct SurfaceHandle {std::shared_ptr<RenderStats> state;};
API void* kc_surface_create(void* pointer){
    auto* window=static_cast<QQuickWindow*>(pointer);if(!window)return nullptr;
    auto state=std::make_shared<RenderStats>();
    new RenderAdmission(window,state);
    QObject::connect(window,&QQuickWindow::beforeFrameBegin,window,[state]{state->inFlight=true;state->begin=Clock::now();},Qt::DirectConnection);
    QObject::connect(window,&QQuickWindow::beforeSynchronizing,window,[state]{state->sync=Clock::now();state->sampleSources();},Qt::DirectConnection);
    QObject::connect(window,&QQuickWindow::afterSynchronizing,window,[state]{state->synchronize=ms(state->sync,Clock::now());},Qt::DirectConnection);
    QObject::connect(window,&QQuickWindow::beforeRendering,window,[state,window]{state->prepare(window);},Qt::DirectConnection);
    QObject::connect(window,&QQuickWindow::afterRendering,window,[state]{state->complete();},Qt::DirectConnection);
    QObject::connect(window,&QQuickWindow::afterFrameEnd,window,[state]{state->submit=ms(state->begin,Clock::now());++state->frames;state->inFlight=false;},Qt::DirectConnection);
    QObject::connect(window,&QQuickWindow::sceneGraphInvalidated,window,[state]{state->reset();},Qt::DirectConnection);
    return new SurfaceHandle{state};
}
API void kc_surface_read(void* handle,double* output){
    if(!handle||!output)return;auto s=static_cast<SurfaceHandle*>(handle)->state;
    output[0]=double(s->frames.load());output[1]=s->record.load();output[2]=s->synchronize.load();output[3]=s->submit.load();output[4]=s->gpu.load();
    output[5]=double(s->replaced.load());output[6]=double(s->observed.load());
    output[7]=double(s->deferred.load());output[8]=s->inFlight?1:0;
}
API void kc_surface_release(void* handle){delete static_cast<SurfaceHandle*>(handle);}
struct ProbeHandle {std::shared_ptr<RenderStats> surface;std::shared_ptr<FrameProbe> probe;};
API void* kc_surface_watch(void* handle,void* sinkPointer){
    if(!handle||!sinkPointer)return nullptr;auto state=static_cast<SurfaceHandle*>(handle)->state;auto probe=std::make_shared<FrameProbe>();
    auto sink=static_cast<QVideoSink*>(sinkPointer);
    probe->connection=QObject::connect(sink,&QVideoSink::videoFrameChanged,sink,[probe](const QVideoFrame& frame){if(frame.isValid())++probe->serial;},Qt::DirectConnection);
    {std::lock_guard<std::mutex> lock(state->probeMutex);state->probes.push_back(probe);}
    return new ProbeHandle{state,probe};
}
API void kc_probe_active(void* handle,bool active){if(handle){auto probe=static_cast<ProbeHandle*>(handle)->probe;if(probe->active.exchange(active)!=active)++probe->epoch;}}
API void kc_probe_release(void* handle){
    if(!handle)return;auto h=static_cast<ProbeHandle*>(handle);QObject::disconnect(h->probe->connection);
    {std::lock_guard<std::mutex> lock(h->surface->probeMutex);auto& probes=h->surface->probes;probes.erase(std::remove(probes.begin(),probes.end(),h->probe),probes.end());}
    delete h;
}

static void text(QSGTextNode* node,const QString& value,QPointF at,int pixels,bool bold=false){
    QFont font(QStringLiteral("Segoe UI"));font.setPixelSize(pixels);font.setBold(bold);
    QTextLayout layout(value,font);layout.beginLayout();auto line=layout.createLine();line.setLineWidth(10000);layout.endLayout();
    node->addTextLayout(at,&layout);
}
struct RulerNode:QSGNode {
    QSGNode* ticks=new QSGNode();QSGSimpleRectNode* cursor=new QSGSimpleRectNode();QSGTextNode* clock;
    double pps=-1,offset=-1,width=-1,height=-1;QRgb color=0,bg=0;QString stamp;
    explicit RulerNode(QQuickWindow* window){appendChildNode(ticks);clock=window->createTextNode();appendChildNode(clock);appendChildNode(cursor);}
};
class Ruler:public QQuickItem {
public:
    double pps=20,offset=0,at=0,bodyX=186,bodyY=28;QColor foreground{QStringLiteral("#b7bac1")},background{QStringLiteral("#26272c")};QString stamp;
    explicit Ruler(QQuickItem* parent):QQuickItem(parent){setFlag(ItemHasContents);setZ(1000000);}
protected:
    QSGNode* updatePaintNode(QSGNode* previous,UpdatePaintNodeData*) override {
        auto n=static_cast<RulerNode*>(previous);if(!n)n=new RulerNode(window());
        if(n->pps!=pps||n->offset!=offset||n->width!=width()||n->height!=bodyY||n->color!=foreground.rgba()||n->bg!=background.rgba()){
            while(auto child=n->ticks->firstChild()){n->ticks->removeChildNode(child);delete child;}
            auto bg=new QSGSimpleRectNode(QRectF(bodyX,0,std::max(0.,width()-bodyX),bodyY),background);n->ticks->appendChildNode(bg);
            auto clip=new QSGClipNode();clip->setIsRectangular(true);clip->setClipRect(QRectF(bodyX,0,std::max(0.,width()-bodyX),bodyY));n->ticks->appendChildNode(clip);
            auto labels=window()->createTextNode();labels->setColor(foreground);clip->appendChildNode(labels);
            double major=600;for(double step:{1.,5.,10.,15.,30.,60.,120.,300.,600.})if(step*pps>=75){major=step;break;}
            int divisions=std::max(2,std::min(20,int(std::round(major*pps/8))));double minor=major/divisions;
            auto first=std::max(0LL,static_cast<long long>(std::floor(offset/(pps*minor)))-1);
            int count=std::min(2048,3+int(std::ceil((width()-bodyX)/std::max(1.,pps*minor))));
            for(int i=0;i<count;++i){
                auto unit=first+i;double moment=unit*minor;double x=bodyX+std::round(moment*pps)-offset;bool isMajor=unit%divisions==0;
                double h=isMajor?12:(unit%(std::max(1,divisions/2))==0?8:4);
                clip->appendChildNode(new QSGSimpleRectNode(QRectF(x,bodyY-h,1,h),foreground));
                if(isMajor){int seconds=int(std::round(moment));text(labels,QStringLiteral("%1:%2").arg(seconds/60,2,10,QChar('0')).arg(seconds%60,2,10,QChar('0')),QPointF(x+4,0),11);}
            }
            n->pps=pps;n->offset=offset;n->width=width();n->height=bodyY;n->color=foreground.rgba();n->bg=background.rgba();
        }
        if(n->stamp!=stamp){n->clock->clear();n->clock->setColor(foreground);text(n->clock,stamp,QPointF(16,0),15,true);n->stamp=stamp;}
        double x=bodyX+at*pps-offset;n->cursor->setRect(QRectF(x>=bodyX?x:-100,bodyY-7,1,7));n->cursor->setColor(QColor(QStringLiteral("#ed5060")));
        return n;
    }
};
API void* kc_ruler_create(void* parent){return parent?new Ruler(static_cast<QQuickItem*>(parent)):nullptr;}
API void kc_ruler_view(void* handle,double width,double pps,double offset,double at,double bodyX,double bodyY,const char* stamp,unsigned foreground,unsigned background){
    if(!handle)return;auto item=static_cast<Ruler*>(handle);item->setWidth(width);item->setHeight(bodyY);item->pps=pps;item->offset=offset;item->at=at;item->bodyX=bodyX;item->bodyY=bodyY;item->stamp=QString::fromUtf8(stamp);item->foreground=QColor::fromRgba(foreground);item->background=QColor::fromRgba(background);item->update();
}

struct PlayerState:std::enable_shared_from_this<PlayerState> {
    QThread* thread=nullptr;QObject* driver=nullptr;QMediaPlayer* player=nullptr;
    QVideoSink* sink=nullptr;
    std::atomic<bool> closing{false},queued{false},seekDirty{false};
    std::atomic<qint64> position{0},seek{0};
    std::atomic<int> status{int(QMediaPlayer::LoadingMedia)},playback{int(QMediaPlayer::StoppedState)},wanted{int(QMediaPlayer::PausedState)},error{0};
    std::atomic<double> rate{1},seekElapsed{0};
    std::atomic<unsigned long long> loaded{0},frames{0};
    std::mutex messageMutex;std::string message;
    std::atomic<double> seekStarted{0};std::atomic<bool> waitingSeek{false},finished{false};
    void schedule(){
        if(closing||queued.exchange(true))return;
        auto self=shared_from_this();
        QMetaObject::invokeMethod(driver,[self]{self->queued=false;if(!self->closing)self->apply();},Qt::QueuedConnection);
    }
    void apply(){
        if(!player)return;
        auto newRate=rate.load();if(player->playbackRate()!=newRate)player->setPlaybackRate(newRate);
        if(seekDirty.exchange(false)){
            waitingSeek=true;seekStarted=nowMs();
            if(player->mediaStatus()!=QMediaPlayer::LoadingMedia)player->setPosition(seek.load());
        }
        auto state=wanted.load();
        if(state==int(QMediaPlayer::PlayingState)&&player->playbackState()!=QMediaPlayer::PlayingState)player->play();
        if(state!=int(QMediaPlayer::PlayingState)&&player->playbackState()==QMediaPlayer::PlayingState)player->pause();
    }
    void close(){
        if(closing.exchange(true))return;
        auto self=shared_from_this();
        QMetaObject::invokeMethod(driver,[self]{
            if(self->player){self->player->setVideoSink(nullptr);self->player->stop();delete self->player;self->player=nullptr;}
            self->driver->deleteLater();self->thread->quit();
        },Qt::QueuedConnection);
    }
};
struct PlayerHandle {std::shared_ptr<PlayerState> state;};
API void* kc_player_create(void* videoSink,const wchar_t* path){
    if(!videoSink||!path)return nullptr;
    auto s=std::make_shared<PlayerState>();s->sink=static_cast<QVideoSink*>(videoSink);
    auto thread=new QThread();thread->setObjectName(QStringLiteral("KineticCut-native-video"));
    ++activePlayers;
    s->thread=thread;s->driver=new QObject();s->driver->moveToThread(thread);
    QObject::connect(thread,&QThread::finished,thread,&QObject::deleteLater);
    QObject::connect(thread,&QThread::finished,thread,[s]{s->finished=true;--activePlayers;},Qt::DirectConnection);
    const auto source=QUrl::fromLocalFile(QString::fromWCharArray(path));
    QMetaObject::invokeMethod(s->driver,[s,source]{
        if(s->closing)return;
        s->player=new QMediaPlayer(s->driver);s->player->setVideoSink(s->sink);
        s->player->setActiveAudioTrack(-1);
        QObject::connect(s->player,&QMediaPlayer::positionChanged,s->driver,[s](qint64 p){s->position=p;});
        QObject::connect(s->player,&QMediaPlayer::playbackStateChanged,s->driver,[s](QMediaPlayer::PlaybackState v){s->playback=int(v);});
        QObject::connect(s->player,&QMediaPlayer::mediaStatusChanged,s->driver,[s](QMediaPlayer::MediaStatus v){
            s->status=int(v);
            if(v==QMediaPlayer::LoadedMedia){++s->loaded;if(s->waitingSeek)s->player->setPosition(s->seek.load());s->apply();}
        });
        QObject::connect(s->player,&QMediaPlayer::errorOccurred,s->driver,[s](QMediaPlayer::Error e,const QString& text){s->error=int(e);std::lock_guard<std::mutex> lock(s->messageMutex);s->message=text.toStdString();});
        // This native callback performs no image conversion and never waits for
        // the UI. Queued frames are not retained by the control component.
        QObject::connect(s->sink,&QVideoSink::videoFrameChanged,s->driver,[s](const QVideoFrame& frame){
            if(!frame.isValid()||s->closing)return;++s->frames;
            if(s->waitingSeek&&frame.startTime()>=0&&frame.endTime()>=s->seek.load()*1000-2000){s->seekElapsed=nowMs()-s->seekStarted.load();s->waitingSeek=false;}
        },Qt::DirectConnection);
        s->player->setSource(source);s->apply();
    },Qt::QueuedConnection);
    thread->start();return new PlayerHandle{s};
}
API void kc_player_command(void* handle,int operation,double value){
    if(!handle)return;auto s=static_cast<PlayerHandle*>(handle)->state;if(s->closing)return;
    if(operation==0){s->seek=qint64(value);s->seekDirty=true;}
    else if(operation==1)s->wanted=int(value);
    else if(operation==2)s->rate=value;
    s->schedule();
}
API void kc_player_read(void* handle,double* output){
    if(!handle||!output)return;auto s=static_cast<PlayerHandle*>(handle)->state;
    output[0]=double(s->position.load());output[1]=s->status.load();output[2]=s->playback.load();output[3]=s->error.load();output[4]=double(s->loaded.load());output[5]=double(s->frames.load());output[6]=s->seekElapsed.load();output[7]=s->finished?1:0;
}
API void kc_player_error(void* handle,char* output,unsigned capacity){
    if(!handle||!output||!capacity)return;auto s=static_cast<PlayerHandle*>(handle)->state;
    std::lock_guard<std::mutex> lock(s->messageMutex);auto count=std::min<size_t>(capacity-1,s->message.size());memcpy(output,s->message.data(),count);output[count]=0;
}
API void kc_player_release(void* handle){
    if(!handle)return;auto* h=static_cast<PlayerHandle*>(handle);h->state->close();delete h;
}
API void kc_player_stop(void* handle){if(handle)static_cast<PlayerHandle*>(handle)->state->close();}
API unsigned kc_players_active(){return activePlayers.load();}
API unsigned kc_qt_abi(){return QT_VERSION;}
API unsigned kc_engine_abi(){return 3;}
#include "timeline_scene.inc"
