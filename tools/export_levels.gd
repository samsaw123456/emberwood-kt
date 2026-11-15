extends SceneTree
func _initialize() -> void:
 call_deferred(&"run")
func values(entry: Array) -> String:
 var result := PackedStringArray()
 for value in entry:
  result.append(str(value).replace("\t", " ").replace("\n", " "))
 return "\t".join(result)
func run() -> void:
 var file := FileAccess.open(OS.get_cmdline_user_args()[0], FileAccess.WRITE)
 var route = load("res://tests/test_route.gd")
 for index in 20:
  var level := ForestLevel.new()
  level.stage_index=index
  root.add_child(level)
  file.store_line(values(["LEVEL",index,ForestChapters.TITLES[index],level.world_width,level.scenery_theme,level.gate.x,level.gate.y,level.gate_label,level.secret.x,level.secret.y]))
  for p in level.platforms:
   file.store_line(values(["PLATFORM",p.kind,p.position.x,p.position.y,p.size.x,p.size.y,p.travel.x,p.travel.y]))
  for spike in level.spikes:
   file.store_line(values(["SPIKE",spike.position.x,spike.position.y,spike.size.x,spike.size.y]))
  for kind in ["gems","acorns","camps","mushrooms"]:
   for point in level.get(kind):
    file.store_line(values([{"gems":"GEM","acorns":"ACORN","camps":"CAMP","mushrooms":"MUSHROOM"}[kind],point.x,point.y]))
  for c in level.critters:
   file.store_line(values(["CRITTER",c.kind,c.home.x,c.home.y,c.range,c.speed]))
  for s in level.signs:
   file.store_line(values(["SIGN",s.pos.x,s.pos.y,s.title,s.hint]))
  var steps: Array = route.FOREST_ROUTE if index==0 else ForestChapters.route(index)
  for step in steps:
   file.store_line(values(["ROUTE",step[0],step[1],step[2]]))
  file.store_line("END")
  root.remove_child(level)
  level.free()
 file.close()
 print("Exported 20 exact original layouts and input routes")
 quit()
