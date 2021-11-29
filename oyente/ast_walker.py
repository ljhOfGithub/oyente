class AstWalker:#遍历ast的类
    def walk(self, node, attributes, nodes):
        if isinstance(attributes, dict):
            self._walk_with_attrs(node, attributes, nodes)
        else:
            self._walk_with_list_of_attrs(node, attributes, nodes)

    def _walk_with_attrs(self, node, attributes, nodes):
        if self._check_attributes(node, attributes):#如果
            nodes.append(node)
        else:
            if "children" in node and node["children"]:
                for child in node["children"]:
                    self._walk_with_attrs(child, attributes, nodes)

    def _walk_with_list_of_attrs(self, node, list_of_attributes, nodes):
        if self._check_list_of_attributes(node, list_of_attributes):
            nodes.append(node)
        else:
            if "children" in node and node["children"]:
                for child in node["children"]:
                    self._walk_with_list_of_attrs(child, list_of_attributes, nodes)

    def _check_attributes(self, node, attributes):
        for name in attributes:
            if name == "attributes":#是否是节点的属性
                if "attributes" not in node or not self._check_attributes(node["attributes"], attributes["attributes"]):
                    return False
            else:
                if name not in node or node[name] != attributes[name]:#如果不是所要研究的节点
                    return False#n
        return True

    def _check_list_of_attributes(self, node, list_of_attributes):
        for attrs in list_of_attributes:#检查node列表中是否有list_of_attributes中所有的属性
            if self._check_attributes(node, attrs):
                return True
        return False
