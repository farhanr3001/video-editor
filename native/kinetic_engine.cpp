// Native, bounded timeline queries and latest-frame admission. No Qt/Python
// callback or mutable document enters this component. ABI versioned explicitly.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <vector>

#define KC_API extern "C" __declspec(dllexport)
namespace {
struct Node {
    uint64_t id,priority;double start,end,maximum;
    std::unique_ptr<Node> left,right;
    Node(uint64_t i,double a,double b):id(i),start(a),end(b),maximum(b) {
        uint64_t x=i+0x9e3779b97f4a7c15ULL;
        x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;priority=x^(x>>31);
    }
};
using Tree=std::unique_ptr<Node>;
double maximum(const Tree& n){return n?n->maximum:-std::numeric_limits<double>::infinity();}
void fix(Tree& n){if(n)n->maximum=std::max(n->end,std::max(maximum(n->left),maximum(n->right)));}
bool less(double a,uint64_t i,double b,uint64_t j){return a<b||(a==b&&i<j);}
Tree merge(Tree a,Tree b) {
    if(!a)return b;if(!b)return a;
    if(a->priority<b->priority){a->right=merge(std::move(a->right),std::move(b));fix(a);return a;}
    b->left=merge(std::move(a),std::move(b->left));fix(b);return b;
}
void split(Tree n,double start,uint64_t id,Tree& a,Tree& b) {
    if(!n){a.reset();b.reset();return;}
    if(less(n->start,n->id,start,id)){split(std::move(n->right),start,id,n->right,b);fix(n);a=std::move(n);}
    else {split(std::move(n->left),start,id,a,n->left);fix(n);b=std::move(n);}
}
Tree erase(Tree n,double start,uint64_t id) {
    if(!n)return n;
    if(n->id==id&&n->start==start)return merge(std::move(n->left),std::move(n->right));
    if(less(start,id,n->start,n->id))n->left=erase(std::move(n->left),start,id);
    else n->right=erase(std::move(n->right),start,id);
    fix(n);return n;
}
struct Engine {
    std::mutex mutex;Tree root;std::unordered_map<uint64_t,double> starts;
    uint64_t visited=0,submitted=0,consumed=0,dropped=0,epoch=0;double pending_time=0;
    void query(Node* n,double a,double b,std::vector<uint64_t>& result) {
        if(!n||n->maximum<a)return;++visited;
        query(n->left.get(),a,b,result);
        if(n->start<=b&&n->end>=a)result.push_back(n->id);
        if(n->start<=b)query(n->right.get(),a,b,result);
    }
};
}
KC_API uint32_t kc_abi(){return 2;}
KC_API void* kc_create(){try{return new Engine();}catch(...){return nullptr;}}
KC_API void kc_destroy(void* handle){delete static_cast<Engine*>(handle);}
KC_API int kc_put(void* handle,uint64_t id,double a,double b) {
    if(!handle||!std::isfinite(a)||!std::isfinite(b)||b<a)return 0;
    try {
        auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);
        auto found=e.starts.find(id);if(found!=e.starts.end())e.root=erase(std::move(e.root),found->second,id);
        auto node=std::make_unique<Node>(id,a,b);Tree left,right;
        split(std::move(e.root),a,id,left,right);e.root=merge(merge(std::move(left),std::move(node)),std::move(right));e.starts[id]=a;return 1;
    }catch(...){return -1;}
}
KC_API void kc_remove(void* handle,uint64_t id) {
    if(!handle)return;auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);
    auto found=e.starts.find(id);if(found==e.starts.end())return;
    e.root=erase(std::move(e.root),found->second,id);e.starts.erase(found);
}
KC_API int64_t kc_query(void* handle,double a,double b,uint64_t* output,uint64_t capacity) {
    if(!handle||!std::isfinite(a)||!std::isfinite(b)||b<a)return -1;
    try {
        auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);
        std::vector<uint64_t> result;e.visited=0;e.query(e.root.get(),a,b,result);std::sort(result.begin(),result.end());
        if(output)std::copy_n(result.begin(),std::min<uint64_t>(capacity,result.size()),output);
        return static_cast<int64_t>(result.size());
    }catch(...){return -1;}
}
KC_API int kc_neighbors(void* handle,double at,double* left,double* right) {
    if(!handle||!left||!right||!std::isfinite(at))return 0;
    auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);
    *left=-std::numeric_limits<double>::infinity();*right=std::numeric_limits<double>::infinity();auto n=e.root.get();
    while(n){if(n->start<=at){*left=n->start;n=n->right.get();}else{*right=n->start;n=n->left.get();}}return 1;
}
KC_API double kc_duration(void* handle) {
    if(!handle)return 0;auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);return std::max(0.,maximum(e.root));
}
KC_API uint64_t kc_visited(void* handle) {
    if(!handle)return 0;auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);return e.visited;
}
// A replaced preview request is counted, never enqueued. An edit/seek epoch
// fences older completions without forbidding deliberate backwards seeks.
KC_API uint64_t kc_submit(void* handle,uint64_t epoch,double at) {
    if(!handle||!std::isfinite(at))return 0;auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);
    if(epoch!=e.epoch){e.epoch=epoch;e.consumed=e.submitted;}
    if(e.submitted>e.consumed)++e.dropped;e.pending_time=at;return ++e.submitted;
}
KC_API int kc_take(void* handle,uint64_t* epoch,uint64_t* serial,double* at) {
    if(!handle||!epoch||!serial||!at)return 0;auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);
    if(e.submitted==e.consumed)return 0;e.consumed=e.submitted;*epoch=e.epoch;*serial=e.submitted;*at=e.pending_time;return 1;
}
KC_API uint64_t kc_dropped(void* handle) {
    if(!handle)return 0;auto& e=*static_cast<Engine*>(handle);std::lock_guard<std::mutex> lock(e.mutex);return e.dropped;
}
