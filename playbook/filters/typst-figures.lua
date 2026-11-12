-- Typst output only (Markdown and HTML are not filtered):
--  * an image figures/NAME.svg becomes the native drawing vlo-figure("NAME") from charts.typ,
--    so figure text stays real text in the PDF (the SVG files are exported from the same code);
--  * the italic lead line under the Markdown title is dropped (the title page shows it);
--  * a lead-in paragraph ("Output (8 rows):", "**Classes**", the description above a table)
--    is kept on the same page as the block it introduces (Typst block sticky: true);
--  * a table of at most MAX_KEEP body rows is not split across pages.
local MAX_KEEP = 15

local function raw(s)
  return pandoc.RawBlock("typst", s)
end

local function body_rows(tbl)
  local n = 0
  for _, body in ipairs(tbl.bodies) do
    n = n + #body.body
  end
  return n
end

local function is_leadin(b)
  if b.t ~= "Para" then
    return false
  end
  if #b.content == 1 and b.content[1].t == "Strong" then
    return true
  end
  local s = pandoc.utils.stringify(b)
  return #s < 400 and s:match(":%s*$") ~= nil
end

local FOLLOW = {CodeBlock = true, Table = true, BulletList = true, OrderedList = true,
                Figure = true, BlockQuote = true}

local function keep_blocks(blocks)
  local sticky = {}
  for i = #blocks, 1, -1 do
    local b, nxt = blocks[i], blocks[i + 1]
    if b.t == "Para" and nxt then
      if (is_leadin(b) and (FOLLOW[nxt.t] or sticky[i + 1])) or nxt.t == "Table" then
        sticky[i] = true
      end
    end
  end
  local out = pandoc.List()
  for i, b in ipairs(blocks) do
    if sticky[i] then
      out:insert(raw("#block(sticky: true, width: 100%)["))
      out:insert(b)
      out:insert(raw("]"))
    elseif b.t == "Table" and body_rows(b) <= MAX_KEEP then
      out:insert(raw("#block(breakable: false, width: 100%)["))
      out:insert(b)
      out:insert(raw("]"))
    else
      out:insert(b)
    end
  end
  return out
end

function Pandoc(doc)
  if not FORMAT:match("typst") then
    return nil
  end
  -- front matter under the Markdown title (lead line, related-paper line) is on the title page:
  -- drop every block between the level-1 title (if the filter still sees it) and the next heading
  local i = 1
  if doc.blocks[1] and doc.blocks[1].t == "Header" and doc.blocks[1].level == 1 then
    i = 2
  end
  while doc.blocks[i] and doc.blocks[i].t ~= "Header" do
    doc.blocks:remove(i)
  end
  doc = doc:walk({
    Image = function(img)
      local name = img.src:match("^figures/([%w%-]+)%.svg$")
      if name then
        return pandoc.RawInline("typst", '#vlo-figure("' .. name .. '")')
      end
    end,
  })
  doc = doc:walk({Blocks = keep_blocks})
  return doc
end
