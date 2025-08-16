from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field
from pydantic_mongo import PydanticObjectId
from schemas.types import LocalizedMoney, LocalizedString, SecureValue

if TYPE_CHECKING:
    from schemas.db_models import ProductAdditional, DeliveryService

class ConfigurationSwitch(BaseModel):
    name: LocalizedString
    price: LocalizedMoney = Field(default_factory=lambda: LocalizedMoney.from_dict({"ru": 0, "en": 0}))

    enabled: bool = False
    
    def update(self, base_sw: "ConfigurationSwitch"):
        self.name=base_sw.name
        self.price=base_sw.price

class ConfigurationSwitches(BaseModel):
    label: LocalizedString
    description: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None

    switches: list[ConfigurationSwitch]

    def get_enabled(self):
        """Возвращает список включённых переключателей из списка switches."""
        return [switch for switch in self.switches if switch.enabled]

    @staticmethod
    def calculate_price(switches: list[ConfigurationSwitch]):
        """Возвращает сумму цен всех переданных переключателей."""
        return sum((switch.price for switch in switches), LocalizedMoney())

    def update(self, base_choice: "ConfigurationSwitches"):
        self.label=base_choice.label
        self.description=base_choice.description
        self.photo_id=base_choice.photo_id
        self.video_id=base_choice.video_id
        
        for i, switch in enumerate(base_choice.switches):
            if len(self.switches)-1 < i:
                self.switches.append(switch)
                continue
            self.switches[i].update(switch)
    
    def toggle_by_localized_name(self, name, lang):
        for switch in self.switches:
            if switch.name.get(lang) == name:
                switch.enabled = not switch.enabled
                break 

class ConfigurationChoice(BaseModel):
    label: LocalizedString
    description: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None

    existing_presets: bool = Field(default=False)
    existing_presets_chosen: int = 1
    existing_presets_quantity: int = 0

    is_custom_input: bool = Field(default=False)
    custom_input_text: Optional[str] = None
    
    can_be_blocked_by: List[str] = [] # формат типо 'option/choice'
    blocks_price_determination: bool = Field(default=False)
    price: LocalizedMoney = Field(default_factory=lambda: LocalizedMoney.from_dict({"RUB": 0, "USD": 0}))

    def update(self, base_choice: "ConfigurationChoice"):
        self.label=base_choice.label
        self.description=base_choice.description
        self.photo_id=base_choice.photo_id
        self.video_id=base_choice.video_id
        self.existing_presets=base_choice.existing_presets
        self.existing_presets_quantity=base_choice.existing_presets_quantity
        self.is_custom_input=base_choice.is_custom_input
        self.blocks_price_determination=base_choice.blocks_price_determination
        self.price=base_choice.price
    
    def check_blocked_all(self, options: Dict[str, Any]) -> bool:
        return any(
            self.check_blocked_path(path, options)
            for path in self.can_be_blocked_by
        )
        
    def get_blocking_path(self, options: Dict[str, Any]) -> Optional[str]:
        return next(
            (
                path
                for path in self.can_be_blocked_by
                if self.check_blocked_path(path, options)
            ),
            None
        )
    
    def check_blocked_path(self, path, options: Dict[str, Any]) -> bool:
        *opt_keys, last_key = path.split("/")
        
        option = options.get(opt_keys[0]) if opt_keys else None
        
        chosen = option.get_chosen()
        if option.choices.get(last_key) == chosen and len(opt_keys) == 1:
            return True
        if isinstance(chosen, ConfigurationSwitches) and len(opt_keys) > 1:
            enabled_names = [sw.name.get("en") for sw in chosen.get_enabled()]
            if opt_keys[1] in enabled_names:
                return True
        return False

class ConfigurationOption(BaseModel):
    name: LocalizedString
    text: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None
    chosen: str

    choices: Dict[str, ConfigurationChoice | ConfigurationSwitches]
    
    def get_chosen(self):
        return self.choices.get(self.chosen)
    
    def set_chosen(self, choice: ConfigurationChoice):
        self.chosen = next((key for key, value in self.choices.items() if value == choice), None)
    
    def get_key_by_label(self, label: str, lang: str) -> Optional[str]:
        for key, choice in self.choices.items():
            if hasattr(choice, "label") and choice.label.get(lang) == label:
                return key
    
    def get_by_label(self, label: str, lang: str) -> Optional[ConfigurationChoice | ConfigurationSwitches]:
        for choice in self.choices.values():
            if hasattr(choice, "label") and choice.label.get(lang) == label:
                return choice

    def calculate_price(self):
        conf_choice = self.get_chosen().model_copy(deep=True)
        price = conf_choice.price.model_copy(deep=True) if isinstance(conf_choice, ConfigurationChoice) else LocalizedMoney()
        price += sum((choice.calculate_price(choice.get_enabled()) for choice in self.choices.values() if isinstance(choice, ConfigurationSwitches)), LocalizedMoney())
        return price
    
    def get_switches(self):
        switch_list = []
        for choice in self.choices.values():
            if isinstance(choice, ConfigurationSwitches):
                switch_list.extend(choice.get_enabled())
        return switch_list
                

    def update(self, option: "ConfigurationOption"):
        self.name = option.name
        self.text = option.text
        self.photo_id = option.photo_id
        self.video_id = option.video_id
        
        # Обновляем choices
        for choice_key, base_choice in option.choices.items():
            if choice_key not in option.choices:
                self.choices[choice_key] = base_choice
                continue
            
            self.choices[choice_key].update(base_choice)
        # Удаляем choices, которых больше нет в base
        for choice_key in list(option.choices.keys()):
            if choice_key not in option.choices:
                del option.choices[choice_key]

class ProductConfiguration(BaseModel):
    options: Dict[str, ConfigurationOption]
    additionals: list["ProductAdditional"] = []
    price: LocalizedMoney = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.price: self.update_price()
    
    
    def update(self, base_configuration: "ProductConfiguration", allowed_additionals: List["ProductAdditional"]):
        """
        Обновляет текущую конфигурацию на основе base_configuration,
        сохраняя пользовательские выборы.
        """
        # Обновляем опции
        for key, base_option in base_configuration.options.items():
            if key not in self.options:
                # Если опция новая, просто добавляем
                self.options[key] = base_option
                continue

            self.options[key].update(base_option)

        # Удаляем опции, которых больше нет в base
        for key in list(self.options.keys()):
            if key not in base_configuration.options:
                del self.options[key]

        base_additional_ids = {add.id for add in allowed_additionals}
        self.additionals = [add for add in self.additionals if add.id in base_additional_ids]

    def get_all_options_localized_names(self, lang):
        return [option.name.get(lang) for option in self.options.values()]
    
    def get_option_by_name(self, name, lang):
        return next((key, option) for key, option in self.options.items()
                    if option.name.get(lang) == name)
        
    def get_additionals_ids(self) -> Iterable[PydanticObjectId]:
        return [add.id for add in self.additionals]
    
    def get_localized_names_by_path(self, path, lang) -> List[str]:
        *opt_keys, last_key = path.split("/")
        result = []
        # Получаем опцию
        option = self.options.get(opt_keys[0]) if opt_keys else None
        if not option:
            return result
        # Добавляем имя опции
        result.append(option.name.data.get(lang))
        # Получаем выбор
        choice = option.choices.get(opt_keys[1]) if len(opt_keys) > 1 else option.choices.get(last_key)
        if not choice:
            return result
        # Добавляем имя выбора
        if hasattr(choice, "label"):
            result.append(choice.label.data.get(lang))
        # Если есть переключатель (switch)
        if len(opt_keys) > 2 and hasattr(choice, "switches"):
            if switch := next(
                (
                    sw
                    for sw in choice.switches
                    if sw.name.data.get(
                        "ru", next(iter(sw.name.data.values()), "")
                    )
                    == last_key
                ),
                None,
            ):
                result.append(switch.name.data.get(lang))
        return result
        
    def calculate_additionals_price(self):
        return sum((additional.price.model_copy(deep=True) for additional in self.additionals), LocalizedMoney())
    
    def calculate_options_price(self):
        return sum((option.calculate_price() for option in self.options.values()), LocalizedMoney())
    
    def update_price(self):
        self.price = self.calculate_additionals_price() + self.calculate_options_price()

class DeliveryRequirement(BaseModel):
    name: LocalizedString
    description: LocalizedString
    value: SecureValue = SecureValue() # для заполнения в будущем при конфигурации

class DeliveryRequirementsList(BaseModel):
    name: LocalizedString # типо "По номеру", или "По адресу и ФИО"
    description: LocalizedString
    requirements: list[DeliveryRequirement]

class DeliveryInfo(BaseModel):
    is_foreign: bool = False  # Вне РФ?
    service: Optional["DeliveryService"] = None