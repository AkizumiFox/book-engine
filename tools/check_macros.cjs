/**
 * Asks MathJax, configured exactly as build/render_math.cjs configures it for the book,
 * which control sequences and environments it does not know. Used by
 * tools/check_macros.py; a JSON job on stdin:
 *
 *   {"mathjax": "<MathJax es5 directory>", "macros": {...}, "names": ["cvec", ...],
 *    "environments": ["pmatrix", ...]}
 *
 * Prints one JSON line: {"undefined": [...], "unknown_environments": [...]}.
 * Each name is typeset on its own, so one bad name cannot hide another; an error other
 * than "undefined" (a missing argument, say) means MathJax knows the name.
 */

const fs = require('fs');
const path = require('path');

const job = JSON.parse(fs.readFileSync(0, 'utf8'));

global.MathJax = {
    loader: {
        paths: { mathjax: job.mathjax },
        load: ['adaptors/liteDOM', 'input/tex-full', 'output/chtml'],  // bussproofs needs an output jax
        require,
    },
    tex: {
        packages: { '[+]': ['ams', 'newcommand', 'configmacros', 'boldsymbol', 'mathtools', 'upgreek'] },
        macros: job.macros,
    },
    startup: { typeset: false },
};

require(path.join(job.mathjax, 'startup.js'));

// tex-full includes the noundefined package, which draws an unknown macro in red
// instead of failing; that is caught here as well as a real "Undefined" error.
const errorOf = tex => {
    try {
        const mml = MathJax.tex2mml(tex);
        if (/<mtext mathcolor="red">\\/.test(mml)) return 'Undefined control sequence (drawn in red)';
        const match = mml.match(/data-mjx-error="([^"]*)"/);
        return match ? match[1] : '';
    } catch (error) {
        return String(error && error.message || error);
    }
};

MathJax.startup.promise.then(() => {
    const result = { undefined: [], unknown_environments: [] };
    for (const name of job.names || []) {
        if (/^Undefined control sequence/.test(errorOf('\\' + name))) result.undefined.push(name);
    }
    for (const env of job.environments || []) {
        if (/^Unknown environment/.test(errorOf(`\\begin{${env}}\\end{${env}}`))) result.unknown_environments.push(env);
    }
    process.stdout.write(JSON.stringify(result) + '\n');
}).catch(error => {
    process.stderr.write(String(error && error.stack || error) + '\n');
    process.exit(1);
});
