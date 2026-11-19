"""Application menu data and opaque native identities; no UI implementation."""
from collections import Counter
from dataclasses import dataclass, replace


def signature(properties):
    # Mutable availability/check state is presentation, not command identity.
    return (properties.get('type','standard'),properties.get('label',''),
        properties.get('children-display',''),properties.get('toggle-type',''),
        tuple(tuple(chord) for chord in properties.get('shortcut',[])),
        bool(properties.get('x-nextspace-key-only')),properties.get('x-nextspace-key-source',''))


@dataclass(frozen=True)
class Node:
    native: int
    remote: int
    properties: dict
    children: tuple


class MenuModel:
    def __init__(self):
        self.root = None
        self.nodes = {}
        self.next_identity = 1

    def reconcile(self, layout):
        seen, nodes = set(), {}

        def validate(raw,depth):
            if not isinstance(raw,(tuple,list)) or len(raw)!=3:
                raise ValueError('Invalid D-Bus menu node')
            identifier,props,children = raw
            if (depth>17 or len(seen)>=4097 or not isinstance(identifier,int)
                    or identifier<0 or identifier in seen or not isinstance(props,dict)
                    or not isinstance(children,(tuple,list))):
                raise ValueError('Invalid or excessive D-Bus menu hierarchy')
            seen.add(identifier)
            for key in ('label','type','children-display','toggle-type','x-nextspace-key-source'):
                if key in props and not isinstance(props[key],str):
                    raise ValueError('Invalid D-Bus menu string')
            shortcut=props.get('shortcut',[])
            if (not isinstance(shortcut,(tuple,list)) or any(not isinstance(chord,(tuple,list))
                    or any(not isinstance(key,str) for key in chord) for chord in shortcut)):
                raise ValueError('Invalid D-Bus menu shortcut')
            for child in children:validate(child,depth+1)

        validate(layout,0)

        def visit(raw, previous, depth):
            identifier, props, children = raw
            if previous is None:
                token = self.next_identity
                self.next_identity += 1
            else:
                token = previous.native
            old_children = previous.children if previous else ()
            old_ids = {n.remote:n for n in old_children}
            matched = [old_ids.get(child[0]) for child in children]
            used = {node.native for node in matched if node is not None}
            remaining = [n for n in old_children if n.native not in used]
            old_counts = Counter(signature(n.properties) for n in remaining)
            new_counts = Counter(signature(raw[1]) for raw,node in zip(children,matched) if node is None)
            unique = {signature(n.properties):n for n in remaining if old_counts[signature(n.properties)]==1}
            # Exporters may rebuild every remote object after popupshowing.
            # Reuse an opaque native identity only for a unique sibling match.
            # Ambiguous duplicates receive new identities; stale commands fail.
            for index,(child,node) in enumerate(zip(children,matched)):
                key = signature(child[1])
                if node is None and new_counts[key]==1:
                    matched[index] = unique.get(key)
            descendants = tuple(visit(child,node,depth+1) for child,node in zip(children,matched))
            node = Node(token,identifier,dict(props),descendants)
            nodes[token] = node
            return node

        if layout[0] != 0:
            raise ValueError('D-Bus menu root must be zero')
        previous = self.root or Node(0,0,{},())
        root = visit(layout,previous,0)
        self.root,self.nodes = root,nodes
        return root


def replace_children(root, token, children):
    if root.native == token:
        return replace(root,children=children)
    return replace(root,children=tuple(replace_children(n,token,children) for n in root.children))


def flattened(root):
    result = []
    def visit(node,parent):
        if not node.properties.get('visible',True):
            return
        index = len(result)
        result.append((parent,node))
        for child in node.children:
            visit(child,index)
    if root:
        for child in root.children:
            visit(child,-1)
    return result
