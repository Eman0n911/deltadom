use serde_json::{json, Value};
use std::collections::BTreeSet;

pub fn extract(raw: &str, fields: &[String]) -> Result<Value, String> {
    if raw.len() > 1_048_576 {
        return Err("API body exceeds 1 MiB".into());
    }
    if fields.is_empty() || fields.len() > 32 {
        return Err("specify 1..32 allowed scalar fields".into());
    }
    let value: Value = serde_json::from_str(raw).map_err(|e| e.to_string())?;
    let fields: BTreeSet<String> = fields.iter().cloned().collect();
    let mut tables = vec![];
    let mut truncated = false;
    walk(&value, "", &fields, 0, &mut tables, &mut truncated);
    Ok(json!({"tables":tables,"truncated":truncated}))
}

fn walk(
    v: &Value,
    path: &str,
    fields: &BTreeSet<String>,
    depth: usize,
    out: &mut Vec<Value>,
    truncated: &mut bool,
) {
    if depth > 16 || out.len() >= 8 {
        *truncated = true;
        return;
    }
    match v {
        Value::Array(arr) => {
            if !arr.is_empty() && arr.iter().all(Value::is_object) {
                let columns: Vec<&String> = fields
                    .iter()
                    .filter(|key| {
                        arr.iter().any(|r| {
                            r.get(key.as_str())
                                .is_some_and(|v| !v.is_array() && !v.is_object())
                        })
                    })
                    .collect();
                if !columns.is_empty() {
                    let rows: Vec<Value> = arr
                        .iter()
                        .take(30)
                        .map(|r| {
                            let mut cells = serde_json::Map::new();
                            for k in &columns {
                                if let Some(v) = r.get(k.as_str()) {
                                    if !v.is_array() && !v.is_object() {
                                        cells.insert((*k).clone(), v.clone());
                                    }
                                }
                            }
                            Value::Object(cells)
                        })
                        .collect();
                    if arr.len() > rows.len() {
                        *truncated = true;
                    }
                    out.push(json!({"pointer":path,"columns":columns,"total_rows":arr.len(),"rows":rows}));
                }
            }
            // Scan wrappers and heterogeneous arrays too; bound traversal and report omission.
            if arr.len() > 30 {
                *truncated = true;
            }
            for (i, item) in arr.iter().take(30).enumerate() {
                if item.is_array() || item.is_object() {
                    walk(
                        item,
                        &format!("{path}/{i}"),
                        fields,
                        depth + 1,
                        out,
                        truncated,
                    );
                }
            }
        }
        Value::Object(map) => {
            for (k, val) in map {
                if val.is_array() || val.is_object() {
                    let key = k.replace('~', "~0").replace('/', "~1");
                    walk(
                        val,
                        &format!("{path}/{key}"),
                        fields,
                        depth + 1,
                        out,
                        truncated,
                    );
                }
            }
        }
        _ => (),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nested_arrays_union_and_projection() {
        let out = extract(
            r#"{"a/b":[{"items":[{"name":"a|b\nc","secret":"no"},{"price":3,"name":null}]}]}"#,
            &["name".into(), "price".into()],
        )
        .unwrap();
        let t = &out["tables"][0];
        assert_eq!(t["pointer"], "/a~1b/0/items");
        assert_eq!(t["rows"][0]["name"], "a|b\nc");
        assert!(t["rows"][0].get("secret").is_none());
        assert!(t["rows"][0].get("price").is_none());
        assert_eq!(t["rows"][1]["name"], Value::Null);
    }
}
