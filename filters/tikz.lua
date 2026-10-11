--[[
TikZ Filter
===========
LaTeX output keeps raw TikZ blocks as they are.

HTML output drops raw LaTeX, so each block containing a tikzpicture or tikzcd
environment is replaced by an <img> of tikz/<hash>.svg. The picture source is
written to <tikz-cache-dir>/<hash>.tex; build/tikz.py compiles those files to SVG
after the Pandoc run (no LaTeX is run from inside the filter).
]]

if not FORMAT:match("html") then
    return {}
end

local cache_dir = nil
local asset_prefix = "./"

-- nd is a Fitch-style derivation (a book that ships latex/fitch-book.sty, which defines it):
-- an array, so it is compiled in math mode. filters/fitch.lua, which runs first, draws most
-- derivations in HTML; one reaches this filter only when that is off ("fitch-html": false)
-- or the block could not be read there. Inert in a book without \begin{nd}.
local PICTURE_ENVS = { "tikzpicture", "tikzcd", "nd" }

-- Return the text from the first \begin{env} to the last matching \end{env}, or nil
local function extract_picture(text)
    for _, env in ipairs(PICTURE_ENVS) do
        local first = text:find("\\begin{" .. env .. "}", 1, true)
        if first then
            local last_end = nil
            local search_from = 1
            local closing = "\\end{" .. env .. "}"
            while true do
                local s, e = text:find(closing, search_from, true)
                if not s then break end
                last_end = e
                search_from = e + 1
            end
            if last_end then
                return text:sub(first, last_end)
            end
        end
    end
    return nil
end

local function write_source(hash, picture)
    local path = cache_dir .. "/" .. hash .. ".tex"
    local existing = io.open(path, "r")
    if existing then
        existing:close()
        return
    end
    local f = io.open(path, "w")
    if not f then
        io.stderr:write("Warning: cannot write TikZ source to " .. path .. "\n")
        return
    end
    f:write(picture)
    f:close()
end

-- Text of the node labels in a picture ("node[right] {$x$}" -> "x"), for alt text
local function node_labels(picture)
    local labels = {}
    -- node[opts] {text}, node {text}, and \node[opts] (name) at (x, y) {text};
    for label in picture:gmatch("node%s*%b[]%s*(%b{})") do table.insert(labels, label) end
    for label in picture:gmatch("node%s*(%b{})") do table.insert(labels, label) end
    for label in picture:gmatch("\\node[^;{]-(%b{})%s*;") do table.insert(labels, label) end
    local cleaned, seen = {}, {}
    for _, label in ipairs(labels) do
        -- TeX commands keep their names (\theta -> theta, \A -> A); braces and $ go
        local text = label:sub(2, -2):gsub("%$", ""):gsub("\\(%a+)%s*", "%1 "):gsub("[{}]", "")
        text = text:gsub("%s+", " "):gsub("^%s+", ""):gsub("%s+$", ""):gsub(" ([_^])", "%1")
        -- a lone symbol name (subseteq, to) says little; skip repeats
        if text ~= "" and not seen[text] and not text:match("^%a%a%a+$") then
            seen[text] = true
            table.insert(cleaned, text)
        end
    end
    return cleaned
end

-- Alt text: the enclosing environment's title (if any) and the figure's labels
local function alt_text(picture, context_title)
    local alt = "Diagram"
    if context_title and context_title ~= "" then
        alt = alt .. ": " .. context_title
    end
    local labels = node_labels(picture)
    if #labels > 0 then
        alt = alt .. ". Labels: " .. table.concat(labels, ", ")
    end
    return alt
end

local function RawBlock(block, context_title)
    if block.format ~= "tex" and block.format ~= "latex" then return nil end
    local picture = extract_picture(block.text)
    if not picture then return nil end

    local is_derivation = picture:sub(1, 10) == "\\begin{nd}"
    if is_derivation then picture = "$" .. picture .. "$" end
    local hash = pandoc.utils.sha1(picture)
    write_source(hash, picture)

    -- The image description becomes its alt text (in a Plain block, not a captioned figure)
    local alt = is_derivation and "Derivation" or alt_text(picture, context_title)
    local image = pandoc.Image({pandoc.Str(alt)},
        asset_prefix .. "tikz/" .. hash .. ".svg", "", pandoc.Attr("", {"tikz"}, {}))
    return pandoc.Div({pandoc.Plain({image})}, pandoc.Attr("", {"tikz-figure"}, {}))
end

-- The "[Title]" line that starts a theorem-like environment
local function div_title(div)
    local first = div.content[1]
    if not first or (first.t ~= "Para" and first.t ~= "Plain") then return nil end
    local text = pandoc.utils.stringify(first)
    return text:match("^%[(.-)%]$") or text:match("^%[(.-)%]")
end

local function Meta(meta)
    if meta["tikz-cache-dir"] then
        cache_dir = pandoc.utils.stringify(meta["tikz-cache-dir"])
    end
    if meta["asset-prefix"] then
        asset_prefix = pandoc.utils.stringify(meta["asset-prefix"])
    end
end

return {
    { Meta = Meta },
    -- Innermost titled environments first (filters run bottom-up), then pictures outside any
    { Div = function(div)
        if not cache_dir then return nil end
        local title = div_title(div)
        if not title then return nil end
        div.content = div.content:walk { RawBlock = function(block) return RawBlock(block, title) end }
        return div
    end },
    { RawBlock = function(block)
        if not cache_dir then return nil end
        return RawBlock(block)
    end },
}
