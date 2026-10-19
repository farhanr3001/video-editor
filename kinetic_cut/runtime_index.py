"""Edit-aware interval indexes. Playback queries never traverse the document.

The serialized model stays ordinary dataclasses/lists. Runtime observers are
weak, excluded from snapshots, and update one interval when a clip is dragged.
"""
import bisect
import copy
import math
import weakref


class IndexedRecord:
    _interval_fields=frozenset(('start','duration','end','track','id','media_id','role','muted'))
    def __setattr__(self,name,value):
        old=self.__dict__.get(name,_MISSING)
        object.__setattr__(self,name,value)
        if name.startswith('_') or old is _MISSING or old==value:return
        for ref in tuple(self.__dict__.get('_index_owners',())):
            owner=ref()
            if owner is not None:owner._record_changed(self,name)
    def _bind_index(self,owner):
        refs=[r for r in self.__dict__.get('_index_owners',()) if r() is not None]
        if not any(r() is owner for r in refs):refs.append(weakref.ref(owner))
        object.__setattr__(self,'_index_owners',refs)
    def _unbind_index(self,owner):
        object.__setattr__(self,'_index_owners',[r for r in self.__dict__.get('_index_owners',()) if r() is not None and r() is not owner])
    def restore_edit_state(self,original):
        for name,value in copy.deepcopy(original.__dict__).items():
            if not name.startswith('_'):setattr(self,name,value)
    def __copy__(self):
        result=type(self).__new__(type(self))
        result.__dict__.update({k:v for k,v in self.__dict__.items() if k!='_index_owners'})
        return result
    def __deepcopy__(self,memo):
        result=type(self).__new__(type(self));memo[id(self)]=result
        result.__dict__.update({k:copy.deepcopy(v,memo) for k,v in self.__dict__.items() if k!='_index_owners'})
        return result


_MISSING=object()


class IndexedList(list):
    def __init__(self,values=(),owner=None,kind='timeline'):
        super().__init__(values);self._owner=weakref.ref(owner) if owner is not None else None;self._kind=kind
        self._bind(self)
    def _bind(self,values):
        owner=self._owner() if self._owner else None
        # Immutable Undo snapshots reuse unchanged records. They must not add
        # live mutation observers to every shared record on every commit.
        if owner is not None and not owner.__dict__.get('_history_snapshot',False):
            for value in values:
                if isinstance(value,IndexedRecord):value._bind_index(owner)
    def _changed(self,values=()):
        owner=self._owner() if self._owner else None
        if owner is not None and getattr(owner,self._kind,None) is self:
            self._bind(values);owner._list_changed(self._kind)
    def append(self,value):super().append(value);self._changed((value,))
    def extend(self,values):values=list(values);super().extend(values);self._changed(values)
    def insert(self,at,value):super().insert(at,value);self._changed((value,))
    def pop(self,*args):value=super().pop(*args);self._changed();return value
    def remove(self,value):super().remove(value);self._changed()
    def clear(self):super().clear();self._changed()
    def reverse(self):super().reverse();self._changed()
    def sort(self,*args,**kwargs):super().sort(*args,**kwargs);self._changed()
    def __setitem__(self,key,value):
        values=list(value) if isinstance(key,slice) else (value,)
        super().__setitem__(key,values if isinstance(key,slice) else value);self._changed(values)
    def __delitem__(self,key):super().__delitem__(key);self._changed()
    def __iadd__(self,values):self.extend(values);return self
    def __imul__(self,n):super().__imul__(n);self._changed(self);return self
    def __deepcopy__(self,memo):
        result=[];memo[id(self)]=result;result.extend(copy.deepcopy(v,memo) for v in self);return result


class IntervalTree:
    """Deterministic augmented treap, logarithmic updates and overlap queries."""
    def __init__(self):self.root=None;self.records={};self.visited=0
    @staticmethod
    def _max(node):return node.maximum if node else -math.inf
    def _fix(self,node):
        if node:node.maximum=max(node.end,self._max(node.left),self._max(node.right))
        return node
    def _merge(self,a,b):
        if a is None:return b
        if b is None:return a
        if a.priority<b.priority:a.right=self._merge(a.right,b);return self._fix(a)
        b.left=self._merge(a,b.left);return self._fix(b)
    def _split(self,node,key):
        if node is None:return None,None
        if node.key<key:
            a,b=self._split(node.right,key);node.right=a;return self._fix(node),b
        a,b=self._split(node.left,key);node.left=b;return a,self._fix(node)
    def _erase(self,node,key):
        if node is None:return None
        if node.key==key:return self._merge(node.left,node.right)
        if key<node.key:node.left=self._erase(node.left,key)
        else:node.right=self._erase(node.right,key)
        return self._fix(node)
    def put(self,ordinal,start,end,value):
        old=self.records.pop(ordinal,None)
        if old:self.root=self._erase(self.root,old.key)
        if not math.isfinite(start) or not math.isfinite(end) or end<start:return
        node=_Node(ordinal,start,end,value);self.records[ordinal]=node
        a,b=self._split(self.root,node.key);self.root=self._merge(self._merge(a,node),b)
    def query(self,left,right):
        result=[];self.visited=0
        def visit(node):
            if node is None or node.maximum<left:return
            self.visited+=1
            if node.left:visit(node.left)
            if node.start<=right and node.end>=left:result.append((node.ordinal,node.value))
            if node.start<=right:visit(node.right)
        visit(self.root);result.sort(key=lambda x:x[0]);return [v for _,v in result]
    def remove(self,ordinal):
        old=self.records.pop(ordinal,None)
        if old:self.root=self._erase(self.root,old.key)
    @property
    def duration(self):return max(0.,self._max(self.root))
    def neighbors(self,at):
        node=self.root;left=-math.inf;right=math.inf
        while node:
            if node.start<=at:left=node.start;node=node.right
            else:right=node.start;node=node.left
        return left,right


class _Node:
    __slots__=('ordinal','start','end','value','key','priority','left','right','maximum')
    def __init__(self,ordinal,start,end,value):
        self.ordinal=ordinal;self.start=start;self.end=end;self.value=value;self.key=(start,ordinal)
        # SplitMix64 avoids degenerate trees for sequential timeline ordinals.
        x=(ordinal+0x9e3779b97f4a7c15)&0xffffffffffffffff
        x=((x^(x>>30))*0xbf58476d1ce4e5b9)&0xffffffffffffffff
        x=((x^(x>>27))*0x94d049bb133111eb)&0xffffffffffffffff
        self.priority=x^(x>>31);self.left=self.right=None;self.maximum=end


PythonIntervalTree=IntervalTree
from .native_engine import LIB,NativeIntervalTree
if LIB is not None:IntervalTree=NativeIntervalTree


class ProjectIndex:
    def __init__(self,project):
        self.project=weakref.ref(project);self.trees={};self.locations={};self.revision=0;self.active_cache=None
        self.media={m.id:m for m in project.media};self.items={i.id:i for i in project.timeline}
        self.transitions={t.id:t for t in project.transitions};self.edges=IntervalTree();self._edge_slots={}
        self.link_counts={};self._links={}
        self.track_items={};self._track_locations={}
        self.members={kind:{id(item):item for item in getattr(project,kind)} for kind in ('timeline','captions','transitions','media')}
        self.order={};self.next_slot={};self.next_edge_slot=0
        for item in project.timeline:self._update_link(item);self._update_track(item)
        for kind in ('timeline','captions','transitions'):
            tree=IntervalTree();self.trees[kind]=tree
            self.order[kind]={id(item):ordinal for ordinal,item in enumerate(getattr(project,kind))}
            for ordinal,item in enumerate(getattr(project,kind)):
                self.locations[id(item)]=(kind,ordinal);tree.put(ordinal,item.start,self.end(item),item)
                self._edge_slots[id(item)]=self.next_edge_slot;self.next_edge_slot+=4;self._update_edges(item)
            self.next_slot[kind]=len(getattr(project,kind))
        self.rebuilds=1;self.queries=0;self.updates=0
    def replace(self,kind):
        project=self.project();values=getattr(project,kind);previous=self.members[kind];current={id(item):item for item in values}
        for identity in previous.keys()-current.keys():
            item=previous[identity];item._unbind_index(project)
            if kind=='timeline':self._remove_track(identity)
            location=self.locations.pop(identity,None)
            if location:
                self.trees[kind].remove(location[1]);base=self._edge_slots.pop(identity)
                for offset in range(4):self.edges.remove(base+offset)
            link=self._links.pop(identity,None)
            if link:
                count=self.link_counts.get(link,0)-1
                if count>0:self.link_counts[link]=count
                else:self.link_counts.pop(link,None)
        if kind!='media':
            for identity in current.keys()-previous.keys():
                item=current[identity];slot=self.next_slot[kind];self.next_slot[kind]+=1
                self.locations[identity]=(kind,slot);self.trees[kind].put(slot,item.start,self.end(item),item)
                self._edge_slots[identity]=self.next_edge_slot;self.next_edge_slot+=4;self._update_edges(item)
                if kind=='timeline':self._update_link(item);self._update_track(item)
                self.updates+=1
            self.order[kind]={id(item):ordinal for ordinal,item in enumerate(values)}
        self.members[kind]=current
        if kind=='timeline':self.items={item.id:item for item in values}
        elif kind=='media':self.media={item.id:item for item in values}
        elif kind=='transitions':self.transitions={item.id:item for item in values}
        self.revision+=1;self.active_cache=None
    @staticmethod
    def end(item):return item.end if hasattr(item,'end') else item.start+item.duration
    def _remove_track(self,identity):
        previous=self._track_locations.pop(identity,None)
        if previous in self.track_items:
            self.track_items[previous].pop(identity,None)
            if not self.track_items[previous]:self.track_items.pop(previous)
    def _update_track(self,item):
        identity=id(item);previous=self._track_locations.get(identity)
        if previous==item.track:return
        self._remove_track(identity)
        self.track_items.setdefault(item.track,{})[identity]=item;self._track_locations[identity]=item.track
    def _update_link(self,item):
        previous=self._links.get(id(item))
        current=item.group_id if item.link_id is None else item.link_id
        if previous==current:return
        if previous:self.link_counts[previous]=max(0,self.link_counts.get(previous,0)-1)
        if current:self.link_counts[current]=self.link_counts.get(current,0)+1
        self._links[id(item)]=current
    def _update_edges(self,item):
        base=self._edge_slots[id(item)];end=self.end(item)
        for offset,edge in enumerate((item.start,end,item.start-.75,end+.75)):
            self.edges.put(base+offset,edge,edge,None)
    def update(self,item,name):
        self.revision+=1;self.active_cache=None
        if name=='track' and id(item) in self.members['timeline']:self._update_track(item)
        if name in ('group_id','link_id') and id(item) in self.members['timeline']:self._update_link(item)
        if name not in IndexedRecord._interval_fields:return
        location=self.locations.get(id(item))
        if location:
            kind,ordinal=location;self.trees[kind].put(ordinal,item.start,self.end(item),item)
            self.updates+=1;self._update_edges(item)
        if name in ('id','media_id'):
            project=self.project();self.media={m.id:m for m in project.media};self.items={i.id:i for i in project.timeline};self.transitions={t.id:t for t in project.transitions}
    def query(self,kind,left,right):
        self.queries+=1;values=self.trees[kind].query(left,right)
        values.sort(key=lambda item:self.order[kind][id(item)]);return values
    def active(self,kind,at):
        return [i for i in self.query(kind,at,at) if i.start<=at<self.end(i)]
    def playback(self,at):
        cached=self.active_cache
        if cached and cached[0]<=at<cached[1]:return cached[2]
        # Actual and warm edges update logarithmically during live trims too.
        left,right=self.edges.neighbors(at)
        clips=self.query('timeline',at-.75,at+.75)
        transitions=self.active('transitions',at)
        ids={id(i) for i in clips}
        for transition in transitions:
            for identifier in (transition.left_item_id,transition.right_item_id):
                item=self.items.get(identifier)
                if item is not None and id(item) not in ids:clips.append(item);ids.add(id(item))
        result=(clips,transitions,self.active('captions',at))
        self.active_cache=(left,right,result);return result
    @property
    def duration(self):return max(t.duration for t in self.trees.values())


class IndexedProject:
    _indexed_lists=frozenset(('timeline','media','captions','transitions'))
    def __setattr__(self,name,value):
        if name in self._indexed_lists:
            value=IndexedList(value,self,name);object.__setattr__(self,name,value);self._list_changed(name)
        else:object.__setattr__(self,name,value)
    def _list_changed(self,kind):
        index=self.__dict__.get('_runtime_index')
        if index is not None:index.replace(kind)
        object.__setattr__(self,'_edit_revision',self.__dict__.get('_edit_revision',0)+1)
    def _record_changed(self,item,name):
        object.__setattr__(self,'_edit_revision',self.__dict__.get('_edit_revision',0)+1)
        index=self.__dict__.get('_runtime_index')
        if index is not None:index.update(item,name)
    @property
    def runtime_index(self):
        index=self.__dict__.get('_runtime_index')
        if index is None:index=ProjectIndex(self);object.__setattr__(self,'_runtime_index',index)
        return index
    def __copy__(self):
        result=type(self).__new__(type(self));result.__dict__.update(self.__dict__);result.__dict__['_runtime_index']=None
        return result
    def __deepcopy__(self,memo):
        result=type(self).__new__(type(self));memo[id(self)]=result
        for name,value in self.__dict__.items():
            if name.startswith('_'):continue
            setattr(result,name,copy.deepcopy(value,memo))
        return result
