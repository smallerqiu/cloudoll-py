class objdict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


OP = objdict(
    AND="AND",
    OR="OR",
    ADD="+",
    SUB="-",
    MUL="*",
    DIV="/",
    BIN_AND="&",
    BIN_OR="|",
    XOR="#",
    MOD="%",
    EQ="=",
    LT="<",
    LTE="<=",
    GT=">",
    GTE=">=",
    NE="!=",
    IN="IN",
    NOT_IN="NOT IN",
    IS="IS",
    DESC="DESC",
    ASC="ASC",
    AVG="AVG",
    AS="AS",
    SUM="SUM",
    MAX="MAX",
    MIN="MIN",
    IS_TODAY="IS_TODAY",
    IS_THIS_WEEK="THIS_WEEK",
    IS_THIS_MONTH="THIS_MONTH",
    IS_THIS_YEAR="THIS_YEAR",
    LASTED_HOURS="LASTED_HOURS",
    LASTED_MINUTES="LASTED_MINUTES",
    LASTED_SECONDS="LASTED_SECONDS",
    LASTED_YEARS="LASTED_YEARS",
    LASTED_MONTHS="LASTED_MONTHS",
    LASTED_DAYS="LASTED_DAYS",
    BEFORE_YEARS="BEFORE_YEARS",
    BEFORE_MONTHS="BEFORE_MONTHS",
    BEFORE_DAYS="BEFORE_DAYS",
    BEFORE_HOURS="BEFORE_HOURS",
    BEFORE_MINUTES="BEFORE_MINUTES",
    BEFORE_SECONDS="BEFORE_SECONDS",
    DATE_FORMAT="DATE_FORMAT",
    JSON_CONTAINS_OBJECT="JSON_CONTAINS_OBJECT",
    JSON_CONTAINS_ARRAY="JSON_CONTAINS_ARRAY",
    COUNT="COUNT",
    COUNT_WHEN="COUNT_WHEN",
    SUM_WHEN="SUM_WHEN",
    MAX_WHEN="MAX_WHEN",
    MIN_WHEN="MIN_WHEN",
    AVG_WHEN="AVG_WHEN",
    IS_NOT="IS NOT",
    IS_NOT_NULL="IS NOT NULL",
    IS_NULL="IS NULL",
    LIKE="LIKE",
    NOT_LIKE="NOT LIKE",
    ILIKE="ILIKE",
    BETWEEN="BETWEEN",
    CONTAINS="CONTAINS",
    NOT_BETWEEN="NOT BETWEEN",
    REGEXP="REGEXP",
    IREGEXP="IREGEXP",
    GROUP_CONCAT="GROUP_CONCAT",
    DISTINCT="DISTINCT",
    CONCAT="||",
    BITWISE_NEGATION="~",
)


class FieldBase(object):
    def _op(op, inverse=False):
        def inner(self, rhs):
            if inverse:
                return Expression(rhs, op, self)
            return Expression(self, op, rhs)

        return inner

    def __eq__(self, rhs):
        return Expression(self, OP.EQ, rhs)

    def __ne__(self, rhs):
        return Expression(self, OP.NE, rhs)

    __lt__ = _op(OP.LT)  # <
    __le__ = _op(OP.LTE)  # <=
    __gt__ = _op(OP.GT)  # >
    __ge__ = _op(OP.GTE)  # >=
    __and__ = _op(OP.AND)  # and
    __or__ = _op(OP.OR)  # or

    # 运算
    __add__ = _op(OP.ADD)  # +
    __radd__ = _op(OP.ADD, True)  # +=
    __sub__ = _op(OP.SUB)  # -
    __rsub__ = _op(OP.SUB, True)  # -=
    __mul__ = _op(OP.MUL)  # *
    __rmul__ = _op(OP.MUL, True)  # *=
    __div__ = _op(OP.DIV)  # /
    __rdiv__ = _op(OP.DIV, True)  # /=

    In = _op(OP.IN)  # in
    not_in = _op(OP.NOT_IN)  # not in
    like = _op(OP.LIKE)  # like
    ilike = _op(OP.ILIKE)  # ilike for pg
    not_like = _op(OP.NOT_LIKE)  # not like

    def group_concat(self, *arg):
        return Function(self, OP.GROUP_CONCAT, arg)

    def distinct(self, *arg):
        return Function(self, OP.DISTINCT, arg)

    def desc(self):
        return Expression(self, OP.DESC, None)

    def asc(self):
        return Expression(self, OP.ASC, None)

    def count(self):
        return Function(self, OP.COUNT)

    def count_when(self, *arg):
        """
        input: count_when(A.field > 10 ,1 , 0) \n
        output: count(case when A.field > 10 then 1 else 0 end)
        """
        return Function(self, OP.COUNT_WHEN, arg)

    def max(self):
        return Function(self, OP.MAX)

    def max_when(self, *arg):
        """
        input: max_when(A.field > 10 ,A.field) \n 
        output: max(case when A.field > 10 then A.field end)
        """
        return Function(self, OP.MAX_WHEN, arg)

    def min(self):
        return Function(self, OP.MIN)

    def min_when(self, *arg):
        """
        input: min_when(A.field > 10 ,A.field) \n 
        output: min(case when A.field > 10 then A.field end)
        """
        return Function(self, OP.MIN_WHEN, arg)

    def sum(self):
        return Function(self, OP.SUM)

    def sum_when(self, *arg):
        """
        input: sum_when(A.field > 10 ,1 , 0)\n
        output: sum(case when A.field > 10 then 1 else 0 end)
        """
        return Function(self, OP.SUM_WHEN, arg)

    def avg(self):
        return Function(self, OP.AVG)

    def avg_when(self, *arg):
        """
        input: avg_when(A.field > 10 , A.field)\n
        output: avg(case when A.field > 10 then A.field end)
        """
        return Function(self, OP.AVG_WHEN, arg)

    def date_format(self, args):
        return Function(self, OP.DATE_FORMAT, args)

    def is_today(self):
        return Function(self, OP.IS_TODAY)

    def is_this_week(self):
        return Function(self, OP.IS_THIS_WEEK)

    def is_this_month(self):
        return Function(self, OP.IS_THIS_MONTH)

    def is_this_year(self):
        return Function(self, OP.IS_THIS_YEAR)

    def lasted_hours(self, args):
        return Function(self, OP.LASTED_HOURS, args)

    def lasted_minutes(self, args):
        return Function(self, OP.LASTED_MINUTES, args)

    def lasted_seconds(self, args):
        return Function(self, OP.LASTED_SECONDS, args)

    def lasted_years(self, args):
        return Function(self, OP.LASTED_YEARS, args)

    def lasted_months(self, args):
        return Function(self, OP.LASTED_MONTHS, args)

    def lasted_days(self, args):
        return Function(self, OP.LASTED_DAYS, args)

    def before_months(self, args):
        return Function(self, OP.BEFORE_MONTHS, args)

    def before_years(self, args):
        return Function(self, OP.BEFORE_YEARS, args)

    def before_days(self, args):
        return Function(self, OP.BEFORE_DAYS, args)

    def before_hours(self, args):
        return Function(self, OP.BEFORE_HOURS, args)

    def before_minutes(self, args):
        return Function(self, OP.BEFORE_MINUTES, args)

    def before_seconds(self, args):
        return Function(self, OP.BEFORE_SECOBDS, args)

    def json_contains_object(self, key, value):
        return Function(self, OP.JSON_CONTAINS_OBJECT, (key, value))

    def json_contains_array(self, args):
        return Function(self, OP.JSON_CONTAINS_ARRAY, args)

    def contains(self, args):
        return Function(self, OP.CONTAINS, args)
        # return AO(f"contains({self.full_name},?)", args)

    def As(self, args):
        return Expression(self, OP.AS, args)

    def is_null(self):
        return Expression(self, OP.IS_NULL, None)

    def not_null(self):
        return Expression(self, OP.IS_NOT_NULL, None)

    def between(self, h1, h2):
        return Expression(self, OP.BETWEEN, ExpList(h1, OP.AND, h2))

    def not_between(self, h1, h2):
        return Expression(self, OP.NOT_BETWEEN, ExpList(h1, OP.AND, h2))


class ExpList(FieldBase):
    def __init__(self, lpt, op, rpt):
        self.lpt = lpt
        self.op = op
        self.rpt = rpt

    def sql(self):
        lpt = self.lpt
        rpt = self.rpt

        p = []
        q = []
        if isinstance(lpt, Exception):
            _q, _p = lpt.sql()
            q = q + _q
            p = p + _p
        else:
            q.append("?")
            p.append(lpt)
        q.append(f" {self.op} ")
        if isinstance(rpt, Exception):
            _q, _p = lpt.sql()
            q = q + _q
            p = p + _p
        else:
            q.append("?")
            p.append(lpt)

        return "".join(q), p
        # return f"{lpt.sql() if isinstance(lpt,Expression) else lpt} {self.op} {rpt.sql() if isinstance(rpt,Expression) else rpt}"


def deconstruct(args):
    f = args[0] if len(args) > 0 else None
    v1 = args[1] if len(args) > 1 else 1
    v2 = args[2] if len(args) > 2 and args[2] is not None else 'NULL'
    c = None
    v = None
    if isinstance(f, FieldBase):
        c = f"{f.lhs.full_name} {f.op} ?"
        v = f.rhs
    if isinstance(v1, FieldBase):
        v1 = v1.name
    return c, v, v1, v2


class Function(FieldBase):
    def __init__(self, col, op, rpt=None):
        self.col = col
        self.op = op
        self.rpt = rpt

    def sql(self):
        op = self.op
        col_name = self.col.full_name
        is_field = isinstance(self.rpt, Field)
        # todo:
        if op == OP.DATE_FORMAT:
            return f"{op}({col_name},?)", [self.rpt]
        elif op == OP.IS_TODAY:
            return f"DATE({col_name}) = CURDATE()", None
        elif op == OP.IS_THIS_WEEK:
            return f"WEEK({col_name}, 1) = WEEK(CURDATE(), 1)", None
        elif op == OP.IS_THIS_MONTH:
            return f"MONTH({col_name}) = MONTH(CURDATE())", None
        elif op == OP.IS_THIS_YEAR:
            return f"YEAR({col_name}) = YEAR(CURDATE())", None

        elif op == OP.LASTED_SECONDS:
            return f"{col_name} >= NOW() - INTERVAL {self.rpt} SECOND", None
        elif op == OP.LASTED_MINUTES:
            return f"{col_name} >= NOW() - INTERVAL {self.rpt} MINUTE", None
        elif op == OP.LASTED_HOURS:
            return f"{col_name} >= NOW() - INTERVAL {self.rpt} HOUR", None
        elif op == OP.LASTED_YEARS:
            return f"{col_name} >= NOW() - INTERVAL {self.rpt} YEAR", None
        elif op == OP.LASTED_MONTHS:
            return f"{col_name} >= NOW() - INTERVAL {self.rpt} MONTH", None
        elif op == OP.LASTED_DAYS:
            return f"DATE({col_name}) >= CURDATE() - INTERVAL {self.rpt} DAY", None

        elif op == OP.BEFORE_YEARS:
            return f"{col_name} < NOW() - INTERVAL {self.rpt} YEAR", None
        elif op == OP.BEFORE_MONTHS:
            return f"{col_name} < NOW() - INTERVAL {self.rpt} MONTH", None
        elif op == OP.BEFORE_DAYS:
            return f"{col_name} < NOW() - INTERVAL {self.rpt} DAY", None
        elif op == OP.BEFORE_HOURS:
            return f"{col_name} < NOW() - INTERVAL {self.rpt} HOUR", None
        elif op == OP.BEFORE_MINUTES:
            return f"{col_name} < NOW() - INTERVAL {self.rpt} MINUTE", None
        elif op == OP.BEFORE_SECONDS:
            return f"{col_name} < NOW() - INTERVAL {self.rpt} SECOND", None
        elif op == OP.CONTAINS:
            return f"{col_name} LIKE CONCAT('%%',?,'%%')", [self.rpt]
            # return f"CONTAINS({col_name},?)", [self.rpt]
        elif op == OP.JSON_CONTAINS_OBJECT:
            _k, _v = self.rpt
            key = _k.full_name if isinstance(_k, Field) else f"'{_k}'"
            return f"json_contains({col_name},json_object({key},?))", [_v]
        elif op == OP.JSON_CONTAINS_ARRAY:
            if is_field:
                return f"json_contains({col_name},json_array({self.rpt.full_name}))", None
            return f"json_contains({col_name},json_array(?))", [self.rpt]
        elif op == OP.COUNT:
            return f"COUNT({col_name})", None
        elif op == OP.COUNT_WHEN:
            c, v, v1, v2 = deconstruct(self.rpt)
            return f"COUNT(CASE WHEN {c} THEN {v1} ELSE {v2} END)", [v]
        elif op == OP.SUM:
            return f"SUM({col_name})", None
        elif op == OP.SUM_WHEN:
            c, v, v1, v2 = deconstruct(self.rpt)
            return f"SUM(CASE WHEN {c} THEN {v1} ELSE {v2} END)", [v]
        elif op == OP.AVG:
            return f"AVG({col_name})", None
        elif op == OP.AVG_WHEN:
            c, v, v1, v2 = deconstruct(self.rpt)
            return f"AVG(CASE WHEN {c} THEN {v1} ELSE {v2} END)", [v]
        elif op == OP.MAX:
            return f"MAX({col_name})", None
        elif op == OP.MAX_WHEN:
            c, v, v1, v2 = deconstruct(self.rpt)
            return f"MAX(CASE WHEN {c} THEN {v1} ELSE {v2} END)", [v]
        elif op == OP.MIN:
            return f"MIN({col_name})", None
        elif op == OP.MIN_WHEN:
            c, v, v1, v2 = deconstruct(self.rpt)
            return f"MIN(CASE WHEN {c} THEN {v1} ELSE {v2} END)", [v]
        elif op == OP.GROUP_CONCAT:
            arg = self.rpt
            extra = None
            if len(arg) == 0:
                extra = col_name
            elif len(arg) == 1 and isinstance(arg[0], FieldBase):
                extra = f"{arg[0].op} {arg[0].col.name}"
            else:
                # todo : DISTINCT name ORDER BY name ASC SEPARATOR '; '
                extra = col_name

            return f"GROUP_CONCAT({extra})", None
        elif op == OP.DISTINCT:
            return f"DISTINCT {col_name}", None


class Expression(FieldBase):
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        # self.__value = ""
        # if op in "+-*/|&~" and lhs._value:
        #     cal = f"{lhs._value}{op}"
        #     if isinstance(rhs, FieldBase):
        #         self.__value = str(eval(f"{cal}{rhs._value}"))
        #     else:
        #         self.__value = str(eval(f"{cal}{rhs}"))

    def sql(self):
        l = self.lhs
        r = self.rhs
        is_fun = isinstance(l, Function)
        p = []
        q = []
        if not is_fun:
            q.append("(")
        if isinstance(l, Field):
            q.append(l.full_name)
        elif isinstance(l, Expression):
            _q, _p = l.sql()
            q.append(_q)
            p = p + _p
        elif is_fun:
            _q, _p = l.sql()
            q.append(_q)
            if _p:
                p = p + _p

        q.append(f" {self.op} ")

        if isinstance(r, Field):
            if r._value is not None:
                q.append("?")
                p.append(r._value)
            else:
                q.append(r.full_name)
        elif isinstance(r, FieldBase):
            _q, _p = r.sql()
            q.append(_q)
            if _p:
                p = p + _p
        elif self.op == OP.AS:
            q.append(r)
        elif r is not None:
            q.append("?")
            p.append(r)
        if not is_fun:
            q.append(")")
        q = [str(num) for num in q]
        return "".join(q), p

    # def __str__(self):
    #     return self.__value
    #     cal = f"{self.lhs._value}{self.op}"
    #     if isinstance(self.rhs, FieldBase):
    #         return str(eval(f"{cal}{self.rhs._value}"))
    #     return str(eval(f"{cal}{self.rhs}"))

    def __repr__(self):
        cal = f"{self.lhs.value}{self.op}"
        if isinstance(self.rhs, FieldBase):
            return str(eval(f"{cal}{self.rhs.value}"))
        return str(eval(f"{cal}{self.rhs}"))


class Field(FieldBase):
    def __init__(
        self,
        name,  # 列名
        column_type,  # 类型
        default=None,  # 默认值
        primary_key=False,  # 主键
        charset=None,  # 编码
        max_length=None,  # 长度
        scale_length=None,  # 精度
        auto_increment=False,  # 自增
        NOT_NULL=False,  # 非空
        created_generated=False,  # 创建时for datetime
        update_generated=False,  # 更新时for datetime
        unsigned=False,  # 无符号，没有负数
        comment=None,  # 备注
        **kwargs,
    ):
        super().__init__()
        self.full_name = None
        self._value = None
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.charset = charset
        self.default = default
        self.max_length = max_length
        self.scale_length = scale_length
        self.auto_increment = auto_increment
        self.NOT_NULL = NOT_NULL
        self.created_generated = created_generated
        self.update_generated = update_generated
        self.comment = comment
        self.unsigned = unsigned

    def __str__(self):
        return str(self._value)
        # "<%s, %s:%s>" % (self.__class__.__name__, self.column_type, self.name)
        # return self.name

    def __repr__(self):
        return str(self._value)

    # def __getattr__(self, item):
    #     return self[item]
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
