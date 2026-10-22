//! Exact, compact node rows. Repeated schemas are shared only when they save bytes.
use crate::Node;
use serde_json::{json, Value};
use std::collections::BTreeMap;

pub fn row(n: &Node) -> Value {
    let mut values = vec![
        json!(n.id),
        json!(n.parent),
        json!(n.order),
        json!(n.tag),
        json!(n.text),
        json!(n.attrs),
        json!(n.role),
        json!(n.interactive),
    ];
    let defaults = [json!(""), json!({}), json!(""), json!(false)];
    while values.len() > 4 && values.last() == Some(&defaults[values.len() - 5]) {
        values.pop();
    }
    json!(values)
}

fn flatten(
    n: &Node,
    children: &BTreeMap<u64, Vec<&Node>>,
    parent_index: i64,
    shape: &mut Vec<Value>,
    values: &mut Vec<Value>,
    plain: &mut Vec<Value>,
) {
    let index = shape.len() as i64;
    shape.push(json!([parent_index, n.order, n.tag, n.role, n.interactive]));
    values.push(json!([n.id, n.text, n.attrs]));
    plain.push(row(n));
    if let Some(cs) = children.get(&n.id) {
        for child in cs {
            flatten(child, children, index, shape, values, plain);
        }
    }
}

fn parts(n: &Node, children: &BTreeMap<u64, Vec<&Node>>) -> (Vec<Value>, Vec<Value>, Vec<Value>) {
    let (mut shape, mut values, mut plain) = (vec![], vec![], vec![]);
    flatten(n, children, -1, &mut shape, &mut values, &mut plain);
    shape[0][1] = json!(0);
    (shape, values, plain)
}

fn tree(n: &Node, children: &BTreeMap<u64, Vec<&Node>>, expected_order: usize) -> Value {
    let mut row = vec![json!(n.id), json!(n.tag)];
    if !n.text.is_empty() {
        row.push(json!(n.text));
    }
    if !n.attrs.is_empty() {
        row.push(json!(n.attrs));
    }
    if n.interactive {
        row.push(json!(true));
    }
    if !n.role.is_empty() {
        row.push(json!(["role", n.role]));
    }
    if n.order != expected_order {
        row.push(json!(["order", n.order]));
    }
    row.extend(emit(n.id, children));
    json!(row)
}

fn emit(parent: u64, children: &BTreeMap<u64, Vec<&Node>>) -> Vec<Value> {
    let Some(cs) = children.get(&parent) else {
        return vec![];
    };
    let mut out = vec![];
    let mut i = 0;
    while i < cs.len() {
        let (shape, values, _) = parts(cs[i], children);
        let mut rows = vec![json!([cs[i].order, values])];
        let first = tree(cs[i], children, i);
        let mut plain = vec![first.clone()];
        let mut j = i + 1;
        while j < cs.len() {
            let (other, values, _) = parts(cs[j], children);
            if other != shape {
                break;
            }
            rows.push(json!([cs[j].order, values]));
            plain.push(tree(cs[j], children, j));
            j += 1;
        }
        let table = json!(["table", {"table_parent":parent,"shape":shape,"rows":rows}]);
        if j - i >= 3 && table.to_string().len() < json!(plain).to_string().len() {
            out.push(table);
            i = j;
        } else {
            out.extend(plain);
            i = j;
        }
    }
    out
}

pub fn render(nodes: &[Node]) -> Value {
    let mut children: BTreeMap<u64, Vec<&Node>> = BTreeMap::new();
    for n in nodes {
        children.entry(n.parent).or_default().push(n);
    }
    for cs in children.values_mut() {
        cs.sort_by_key(|n| n.order);
    }
    json!(emit(0, &children))
}

pub fn patch(old: &Node, new: &Node) -> Value {
    let a = serde_json::to_value(old).unwrap();
    let b = serde_json::to_value(new).unwrap();
    let mut changed = serde_json::Map::new();
    for (key, value) in b.as_object().unwrap() {
        if key != "attrs" && a[key] != *value {
            changed.insert(key.clone(), value.clone());
        }
    }
    let mut attrs = serde_json::Map::new();
    for (key, value) in &new.attrs {
        if old.attrs.get(key) != Some(value) {
            attrs.insert(key.clone(), json!(value));
        }
    }
    for key in old.attrs.keys() {
        if !new.attrs.contains_key(key) {
            attrs.insert(key.clone(), Value::Null);
        }
    }
    if !attrs.is_empty() {
        changed.insert("attrs".into(), json!(attrs));
    }
    json!([new.id, changed])
}
