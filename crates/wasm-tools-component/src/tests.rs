use super::*;
use serde_json::Value;

const WIT: &str = r#"
    package test:type-graph@1.0.0;
    interface types {
        resource item {
            create: static func() -> result<item, string>;
            size: func() -> u32;
        }
        record row { label: string, bytes: option<list<u8>> }
        variant cell { text(string), missing }
        inspect: func(value: borrow<item>) -> row;
        consume: func(value: own<item>) -> cell;
    }
    interface api {
        use types.{item, row};
        inspect: func(value: borrow<item>) -> result<row, string>;
    }
    world test { export types; export api; }
"#;

fn component() -> Vec<u8> {
    let module = WasmToolsJs::component_embed(EmbedOpts {
        binary: None,
        wit_source: Some(WIT.into()),
        wit_path: None,
        string_encoding: None,
        dummy: Some(true),
        world: Some("test".into()),
        metadata: None,
        features: None,
    })
    .unwrap();
    WasmToolsJs::component_new(module, None).unwrap()
}

#[test]
fn component_wit_json_preserves_the_full_decoded_graph() {
    let bytes = component();
    let actual: Value =
        serde_json::from_str(&WasmToolsJs::component_wit_json(bytes.clone()).unwrap()).unwrap();
    let DecodedWasm::Component(resolve, world) = wit_component::decode(&bytes).unwrap() else {
        panic!("expected a component");
    };
    assert_eq!(actual["world"], world.index());
    assert_eq!(actual["resolve"], serde_json::to_value(&resolve).unwrap());
    assert!(
        actual["resolve"]["worlds"][world.index()]["exports"]
            .as_object()
            .unwrap()
            .len()
            >= 2
    );

    let types = &actual["resolve"]["types"];
    let interfaces = actual["resolve"]["interfaces"].as_array().unwrap();
    let interface = interfaces
        .iter()
        .find(|value| value["name"] == "types")
        .unwrap();
    let borrowed = interface["functions"]["inspect"]["params"][0]["type"]
        .as_u64()
        .unwrap() as usize;
    let owned = interface["functions"]["consume"]["params"][0]["type"]
        .as_u64()
        .unwrap() as usize;
    assert!(types[borrowed]["kind"]["handle"].get("borrow").is_some());
    assert!(types[owned]["kind"]["handle"].get("own").is_some());
    assert!(
        interface["functions"]["[static]item.create"]["kind"]
            .get("static")
            .is_some()
    );
    assert!(
        interface["functions"]["[method]item.size"]["kind"]
            .get("method")
            .is_some()
    );

    let api = interfaces
        .iter()
        .find(|value| value["name"] == "api")
        .unwrap();
    let alias = api["types"]["item"].as_u64().unwrap() as usize;
    assert_eq!(types[alias]["kind"]["type"], interface["types"]["item"]);
}

#[test]
fn component_wit_json_rejects_invalid_binaries_and_wit_packages() {
    assert!(WasmToolsJs::component_wit_json(vec![]).is_err());
    let malformed = vec![0, 97, 115, 109, 13, 0, 1, 0, 0xff];
    assert!(WasmToolsJs::component_wit_json(malformed).is_err());
    assert!(WasmToolsJs::component_wit_json(wat::parse_str("(module)").unwrap()).is_err());

    let mut package_type = wasm_encoder::ComponentType::new();
    package_type
        .ty()
        .component(&wasm_encoder::ComponentType::new());
    package_type.export(
        "test:empty/empty",
        wasm_encoder::ComponentTypeRef::Component(0),
    );
    let mut types = wasm_encoder::ComponentTypeSection::new();
    types.component(&package_type);
    let mut exports = wasm_encoder::ComponentExportSection::new();
    exports.export("empty", wasm_encoder::ComponentExportKind::Type, 0, None);
    let mut package = wasm_encoder::Component::new();
    package.section(&types).section(&exports);
    let error = WasmToolsJs::component_wit_json(package.finish()).unwrap_err();
    assert!(error.contains("not a WIT package"));
    // Declared input errors must not poison later metadata calls.
    assert!(WasmToolsJs::component_wit_json(component()).is_ok());
}
