import { assert, suite, test } from 'vitest';

import { componentEmbed, componentNew, componentWitJson, parse } from '../src/wasm-tools.js';

const WIT = `
    package test:type-graph;
    interface api {
        resource item;
        inspect: func(value: borrow<item>) -> option<list<u8>>;
        consume: func(value: own<item>);
    }
    world test { export api; }
`;

type TypeGraph = {
    world: number;
    resolve: {
        worlds: Array<{ exports: Record<string, unknown> }>;
        interfaces: Array<{
            name: string;
            functions: Record<string, { params: Array<{ type: number }> }>;
        }>;
        types: Array<{ kind: { handle?: { own?: number; borrow?: number } } }>;
    };
};

suite('Component WIT JSON', () => {
    test('exposes the selected world and distinguishes owned and borrowed resource inputs', async () => {
        const module = await componentEmbed({ witSource: WIT, world: 'test', dummy: true });
        const component = await componentNew(module);
        const graph = JSON.parse(await componentWitJson(component)) as TypeGraph;

        assert.isNumber(graph.world);
        assert.isNotEmpty(graph.resolve.worlds[graph.world].exports);
        const api = graph.resolve.interfaces.find((entry) => entry.name === 'api');
        if (!api) throw new Error('missing api interface');
        const borrowed = api.functions.inspect.params[0].type;
        const owned = api.functions.consume.params[0].type;
        assert.property(graph.resolve.types[borrowed].kind.handle, 'borrow');
        assert.property(graph.resolve.types[owned].kind.handle, 'own');
    });

    test('rejects malformed binaries and core modules without poisoning later calls', async () => {
        await assert.rejects(componentWitJson(new Uint8Array()));
        const malformed = new Uint8Array([0, 97, 115, 109, 13, 0, 1, 0, 0xff]);
        await assert.rejects(componentWitJson(malformed));
        await assert.rejects(componentWitJson(await parse('(module)')));
        const component = await componentNew(await componentEmbed({ witSource: WIT, world: 'test', dummy: true }));
        assert.isObject(JSON.parse(await componentWitJson(component)));
    });
});
