import { mkdir, readFile, writeFile } from "node:fs/promises"
import { registerHooks } from "node:module"
import { basename, dirname, join, resolve } from "node:path"
import { pathToFileURL } from "node:url"

const root = resolve("build.nosync")
const dependency = join(root, "deps/jco-transpile/package")
const shim = join(root, "deps/preview2-shim/package")
// The bootstrap compiler operates on bytes, with a private in-memory filesystem.
// It neither needs the Node filesystem addon nor installs a package dependency tree.
registerHooks({
    resolve(specifier, context, next) {
        if (specifier === "@bytecodealliance/preview2-shim")
            return { url: pathToFileURL(join(shim, "dist/browser/index.js")).href, shortCircuit: true }
        return next(specifier, context)
    },
})
const { WASIShim } = await import(pathToFileURL(join(shim, "dist/common/instantiation.js")))
const { instantiate } = await import(
    pathToFileURL(join(dependency, "vendor/js-component-bindgen-component-instantiation.js"))
)
const imports = new WASIShim().getImportObject()
const compiler = await instantiate(async (name) => {
    if (basename(name) !== name) throw Error("Unexpected bootstrap module path")
    return WebAssembly.compile(await readFile(join(dependency, "vendor", name)))
}, imports)
const bytes = new Uint8Array(await readFile(join(root, "wasm-tools.component.wasm")))
const options = {
    name: "wasm-tools",
    noTypescript: false,
    noNodejsCompat: false,
    base64Cutoff: 0,
    tlaCompat: true,
    validLiftingOptimization: false,
    noNamespacedExports: true,
    multiMemory: true,
    importBindings: { tag: "js" },
    strict: false,
}
const direct = await compiler.generate(bytes, {
    ...options,
    map: ["cli", "clocks", "filesystem", "io", "random", "sockets"].map((name) => [
        `wasi:${name}/*`,
        `@bytecodealliance/preview2-shim/${name}#*`,
    ]),
})
const factory = await compiler.generate(bytes, { ...options, instantiation: { tag: "async" } })
const output = join(root, "package/vendor")
for (const [name, data] of direct.files) {
    if (name.split("/").some((part) => part === ".." || part === "")) throw Error("Unexpected generated filename")
    await mkdir(dirname(join(output, name)), { recursive: true })
    await writeFile(join(output, name), data)
}
for (const [name, data] of factory.files) {
    if (name === "wasm-tools.js" || name === "wasm-tools.d.ts")
        await writeFile(join(output, name.replace("wasm-tools.", "wasm-tools-instantiation.")), data)
    if (name.endsWith(".wasm")) {
        const original = direct.files.find(([file]) => file === name)
        if (!original || !Buffer.from(original[1]).equals(Buffer.from(data)))
            throw Error("Direct/factory core modules differ")
    }
}
const tool = await import(pathToFileURL(join(output, "wasm-tools-instantiation.js")))
const instance = await tool.instantiate(
    async (name) => WebAssembly.compile(await readFile(join(output, name))),
    imports,
)
const fixture = await instance.tools.componentNew(
    instance.tools.componentEmbed({
        witSource:
            "package test:graph; interface api { resource item; inspect: func(value: borrow<item>); consume: func(value: own<item>); } world test { export api; }",
        world: "test",
        dummy: true,
    }),
    undefined,
)
const graph = JSON.parse(await instance.tools.componentWitJson(fixture))
const api = graph.resolve.interfaces.find((item) => item.name === "api")
if (!api) throw Error("Schema export lost interface")
const borrowed = graph.resolve.types[api.functions.inspect.params[0].type].kind.handle
const owned = graph.resolve.types[api.functions.consume.params[0].type].kind.handle
if (!Object.hasOwn(borrowed, "borrow") || !Object.hasOwn(owned, "own"))
    throw Error("Schema export lost resource ownership")
for (const input of [new Uint8Array(), new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0])]) {
    let rejected = false
    try {
        await instance.tools.componentWitJson(input)
    } catch (error) {
        if (!instance._util.isComponentError(error)) throw error
        rejected = true
    }
    if (!rejected) throw Error("Schema export accepted invalid input")
}
JSON.parse(await instance.tools.componentWitJson(fixture))
await instance._util.whenIdle()
instance._util.stop()
await compiler._util.whenIdle()
compiler._util.stop()
console.log("Generated compiler API: full graph, ownership and declared error checks pass")
