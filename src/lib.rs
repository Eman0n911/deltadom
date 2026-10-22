mod collapse;
mod net_filter;

use pyo3::{exceptions::PyValueError, prelude::*};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub id: u64,
    pub parent: u64,
    pub order: usize,
    pub tag: String,
    pub role: String,
    pub text: String,
    pub attrs: BTreeMap<String, String>,
    pub interactive: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Frame {
    pub document: String,
    pub url: String,
    pub nodes: Vec<Node>,
}

fn validate(frame: &Frame) -> Result<(), String> {
    if frame.document.is_empty() || frame.nodes.len() > 50_000 {
        return Err("empty document identity or node limit exceeded".into());
    }
    let mut seen = BTreeSet::from([0]);
    let mut orders = BTreeSet::new();
    let mut depths = BTreeMap::from([(0, 0usize)]);
    for n in &frame.nodes {
        if n.id == 0 || seen.contains(&n.id) || !seen.contains(&n.parent) {
            return Err("IDs must be unique; parents must precede children".into());
        }
        if !orders.insert((n.parent, n.order)) {
            return Err("duplicate sibling order".into());
        }
        let depth = depths[&n.parent] + 1;
        if depth > 256 {
            return Err("semantic tree depth exceeds 256".into());
        }
        depths.insert(n.id, depth);
        seen.insert(n.id);
    }
    Ok(())
}

#[pyclass]
pub struct DeltaSession {
    document: String,
    url: String,
    seq: u64,
    previous: BTreeMap<u64, Node>,
    threshold: f64,
    keyframe_interval: u64,
    last_full: u64,
}

#[pymethods]
impl DeltaSession {
    #[new]
    #[pyo3(signature = (threshold=0.45, keyframe_interval=20))]
    fn new(threshold: f64, keyframe_interval: u64) -> PyResult<Self> {
        if !threshold.is_finite() || !(0.0..=1.0).contains(&threshold) || keyframe_interval == 0 {
            return Err(PyValueError::new_err(
                "invalid threshold or keyframe interval",
            ));
        }
        Ok(Self {
            document: String::new(),
            url: String::new(),
            seq: 0,
            previous: BTreeMap::new(),
            threshold,
            keyframe_interval,
            last_full: 0,
        })
    }

    /// The JSON boundary intentionally copies; this is not a zero-copy API.
    #[pyo3(signature = (frame_json, force_full=false))]
    fn process_frame(&mut self, frame_json: &str, force_full: bool) -> PyResult<String> {
        if frame_json.len() > 16 * 1024 * 1024 {
            return Err(PyValueError::new_err("frame exceeds 16 MiB"));
        }
        let frame: Frame = serde_json::from_str(frame_json).map_err(value_error)?;
        validate(&frame).map_err(value_error)?;
        let current: BTreeMap<u64, Node> = frame.nodes.iter().map(|n| (n.id, n.clone())).collect();
        let upsert: Vec<&Node> = frame
            .nodes
            .iter()
            .filter(|n| self.previous.get(&n.id) != Some(n))
            .collect();
        let removed: Vec<u64> = self
            .previous
            .keys()
            .filter(|id| !current.contains_key(id))
            .copied()
            .collect();
        let union = self.previous.len()
            + current
                .keys()
                .filter(|id| !self.previous.contains_key(id))
                .count();
        let ratio = (upsert.len() + removed.len()) as f64 / union.max(1) as f64;
        let reason = if self.seq == 0 {
            "initial"
        } else if self.document != frame.document {
            "document_changed"
        } else if self.url != frame.url {
            "url_changed"
        } else if force_full {
            "requested"
        } else if self.seq + 1 - self.last_full >= self.keyframe_interval {
            "periodic"
        } else if ratio > self.threshold {
            "change_ratio"
        } else {
            "delta"
        };
        let seq = self.seq + 1;
        let full = reason != "delta";
        let mut result = json!({"version":1, "document":frame.document, "url":frame.url,
            "seq":seq, "base_seq":if full {None} else {Some(self.seq)},
            "kind":if full {"full"} else {"delta"}, "reason":reason, "change_ratio":ratio});
        let mut text = json!({"v":2,"kind":if full {"full"} else {"delta"},
            "document":frame.document,"seq":seq});
        if full {
            result["nodes"] = json!(frame.nodes);
            text["url"] = json!(frame.url);
            text["columns"] = json!([
                "id",
                "parent",
                "order",
                "tag",
                "text",
                "attrs",
                "role",
                "interactive"
            ]);
            text["tree"] = collapse::render(&frame.nodes);
        } else {
            result["upsert"] = json!(upsert);
            result["removed"] = json!(removed);
            text["base"] = json!(self.seq);
            let mut added = vec![];
            let mut patches = vec![];
            for n in &upsert {
                match self.previous.get(&n.id) {
                    Some(old) => patches.push(collapse::patch(old, n)),
                    None => added.push(collapse::row(n)),
                }
            }
            if !added.is_empty() {
                text["add"] = json!(added);
            }
            if !patches.is_empty() {
                text["patch"] = json!(patches);
            }
            if !removed.is_empty() {
                text["remove"] = json!(removed);
            }
        }
        result["text"] = json!(text.to_string() + "\n");
        // Commit only after successful input validation / serialization.
        self.previous = current;
        self.document = frame.document;
        self.url = frame.url;
        self.seq = seq;
        if full {
            self.last_full = seq;
        }
        Ok(result.to_string())
    }

    fn filter_api_json(&self, raw_json: &str, fields: Vec<String>) -> PyResult<String> {
        net_filter::extract(raw_json, &fields)
            .map(|v| v.to_string())
            .map_err(value_error)
    }
}

fn value_error(e: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(e.to_string())
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<DeltaSession>()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    fn node(id: u64, parent: u64, order: usize) -> Node {
        Node {
            id,
            parent,
            order,
            tag: "button".into(),
            role: "button".into(),
            text: format!("item {id}"),
            attrs: BTreeMap::new(),
            interactive: true,
        }
    }
    fn process(s: &mut DeltaSession, doc: &str, nodes: Vec<Node>) -> Value {
        serde_json::from_str(
            &s.process_frame(
                &json!({"document":doc,"url":"http://local/","nodes":nodes}).to_string(),
                false,
            )
            .unwrap(),
        )
        .unwrap()
    }
    #[test]
    fn reorder_and_attribute_changes_are_not_lost() {
        let mut s = DeltaSession::new(1.0, 20).unwrap();
        let a = vec![node(1, 0, 0), node(2, 0, 1)];
        process(&mut s, "d", a.clone());
        let mut b = a.clone();
        b[0].order = 1;
        b[1].order = 0;
        let out = process(&mut s, "d", b.clone());
        assert_eq!(out["upsert"].as_array().unwrap().len(), 2);
        b[0].attrs.insert("disabled".into(), "true".into());
        b[0].role = "menuitem".into();
        assert_eq!(
            process(&mut s, "d", b)["upsert"].as_array().unwrap().len(),
            1
        );
    }
    #[test]
    fn same_url_reload_and_empty_frame() {
        let mut s = DeltaSession::new(1.0, 20).unwrap();
        process(&mut s, "doc1", vec![node(1, 0, 0)]);
        assert_eq!(
            process(&mut s, "doc2", vec![node(1, 0, 0)])["reason"],
            "document_changed"
        );
        assert_eq!(process(&mut s, "doc2", vec![])["removed"], json!([1]));
        assert_eq!(process(&mut s, "doc2", vec![])["upsert"], json!([]));
    }
    #[test]
    fn invalid_input_is_transactional() {
        let mut s = DeltaSession::new(1.0, 20).unwrap();
        process(&mut s, "d", vec![]);
        assert!(s
            .process_frame(
                &json!({"document":"d","url":"x","nodes":[node(1,1,0)]}).to_string(),
                false
            )
            .is_err());
        assert_eq!(process(&mut s, "d", vec![])["seq"], 2);
    }
    #[test]
    fn periodic_and_explicit_resync() {
        let mut s = DeltaSession::new(1.0, 2).unwrap();
        process(&mut s, "d", vec![]);
        process(&mut s, "d", vec![]);
        assert_eq!(process(&mut s, "d", vec![])["reason"], "periodic");
        let raw = json!({"document":"d","url":"http://local/","nodes":[]}).to_string();
        let result: Value = serde_json::from_str(&s.process_frame(&raw, true).unwrap()).unwrap();
        assert_eq!(result["reason"], "requested");
    }
}
